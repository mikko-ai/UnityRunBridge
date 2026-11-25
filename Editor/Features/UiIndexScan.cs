using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor
{
    [BridgeModule]
    public sealed class UiIndexBridgeModule : IBridgeModule
    {
        public string Capability => "ui-index";
        public int Order => 100;
        public bool IsAvailable(IBridgeServiceResolver services) =>
            services != null && services.TryGet(out IUiPrefabIndexer _);

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            services.TryGet(out IUiPrefabIndexer indexer);
            routes.Map("POST", "ui-index/scan", ctx => UiIndexScan.Begin((BridgeRequestContext)ctx, indexer));
            if (services.TryGet(out IIndexedClickBackend clickBackend))
            {
                routes.Map("POST", "ui-index/bind", ctx => UiIndexRuntime.Bind((BridgeRequestContext)ctx));
                routes.Map("POST", "ui-index/resolve", ctx => UiIndexRuntime.Execute((BridgeRequestContext)ctx, clickBackend, false));
                routes.Map("POST", "ui-index/click", ctx => UiIndexRuntime.Execute((BridgeRequestContext)ctx, clickBackend, true));
            }
        }
    }

    internal sealed class UiIndexScan
    {
        internal const int Schema = 1;
        private const int MaxAssets = 100_000;
        private const int MaxBatch = 32;
        private const long MaxOutputBytes = 256L * 1024 * 1024;
        private static UiIndexScan active;

        private readonly JobHandle handle;
        private readonly string root;
        private readonly Dictionary<string, string> known;
        private readonly IUiPrefabIndexer indexer;
        private readonly Stopwatch watch = Stopwatch.StartNew();
        private string[] guids;
        private ulong assetRevision;
        private int next;
        private int scanned;
        private int skipped;
        private int unchanged;
        private int unidentified;
        private int controls;
        private long outputBytes;
        private string artifact;
        private StreamWriter writer;

        private UiIndexScan(JobHandle handle, string root, Dictionary<string, string> known,
            IUiPrefabIndexer indexer)
        {
            this.handle = handle;
            this.root = root;
            this.known = known;
            this.indexer = indexer;
        }

        internal static object Begin(BridgeRequestContext ctx, IUiPrefabIndexer indexer)
        {
            if (!EditorReady())
                return BridgeResponse.Failure("editor_not_ready", "只允许在空闲的编辑模式扫描 UI Prefab");
            if (active != null)
                return BridgeResponse.Failure("already_scanning", "正在扫描 UI Prefab");
            if (ctx.RawBody.Length > 12 * 1024 * 1024)
                return BridgeResponse.Failure("invalid_argument", "索引请求超过大小上限");
            JsonValue body = ctx.Body;
            if (body == null || !body.IsObject || !body.TryGetString("root", out string requested)
                || !TryCanonicalRoot(requested, out string root)
                || !TryReadKnown(body, out Dictionary<string, string> known))
                return BridgeResponse.Failure("invalid_argument", "需要 Assets 下的目录，以及合法的 known GUID/指纹对象");

            JobStartResult start = JobManager.StartJob("ui-index-scan",
                handle => Start(handle, root, known, indexer), timeoutSeconds: 300);
            if (!start.Ok)
                return BridgeResponse.Failure(start.ErrorCode, start.ErrorMessage);
            var response = JsonValue.NewObject();
            response["ok"] = true;
            response["jobId"] = start.JobId;
            return response;
        }

        private static bool TryCanonicalRoot(string value, out string root)
        {
            root = value;
            if (string.IsNullOrEmpty(value) || value.Length > 1024 || value.Any(char.IsControl)
                || value.Contains("\\") || !(value == "Assets" || value.StartsWith("Assets/", StringComparison.Ordinal))
                || value.Split('/').Any(part => part == "" || part == "." || part == "..")
                || !AssetDatabase.IsValidFolder(value))
                return false;
            return value == "Assets" || value == AssetDatabase.GUIDToAssetPath(AssetDatabase.AssetPathToGUID(value));
        }

        private static bool TryReadKnown(JsonValue body, out Dictionary<string, string> known)
        {
            known = new Dictionary<string, string>(StringComparer.Ordinal);
            if (!body.TryGet("known", out JsonValue values))
                return true;
            if (!values.IsObject || values.Count > MaxAssets)
                return false;
            foreach (var entry in values.Properties)
            {
                if (!IsHash(entry.Key) || !entry.Value.IsString || !IsHash(entry.Value.AsString))
                    return false;
                known.Add(entry.Key, entry.Value.AsString);
            }
            return true;
        }

        private static bool IsHash(string value) =>
            value.Length == 32 && value.All(c => (c >= 'a' && c <= 'f') || (c >= '0' && c <= '9'));

        private static bool EditorReady() =>
            !EditorApplication.isPlayingOrWillChangePlaymode && !EditorApplication.isCompiling && !EditorApplication.isUpdating;

        private static void Start(JobHandle handle, string root, Dictionary<string, string> known,
            IUiPrefabIndexer indexer)
        {
            active = new UiIndexScan(handle, root, known, indexer);
            EditorApplication.update += active.Tick;
            AssemblyReloadEvents.beforeAssemblyReload += active.Cleanup;
        }

        private void Tick()
        {
            if (JobManager.GetJob(handle.JobId)?.Status != JobStatus.Running)
            {
                Cleanup();
                return;
            }

            try
            {
                if (!EditorReady())
                {
                    Fail("ui_index_invalidated", "Editor 状态改变，未发布部分索引");
                    return;
                }
                if (guids == null)
                    Initialize();
                if (assetRevision != AssetDatabase.GlobalArtifactDependencyVersion)
                {
                    Fail("ui_index_invalidated", "扫描期间资产导入状态改变，请重新同步");
                    return;
                }
                var budget = Stopwatch.StartNew();
                for (int i = 0; i < MaxBatch && next < guids.Length; i++)
                {
                    ReadAsset(guids[next++]);
                    if (budget.ElapsedMilliseconds >= 6)
                        break;
                }
                if (next == guids.Length)
                {
                    if (assetRevision != AssetDatabase.GlobalArtifactDependencyVersion)
                        Fail("ui_index_invalidated", "扫描期间资产状态改变，请重新同步");
                    else
                        Finish();
                }
            }
            catch (Exception ex)
            {
                Fail("ui_index_scan_failed", ex.Message);
            }
        }

        private void Initialize()
        {
            assetRevision = AssetDatabase.GlobalArtifactDependencyVersion;
            guids = AssetDatabase.FindAssets("t:Prefab", new[] { root }).Distinct().ToArray();
            if (guids.Length > MaxAssets)
                throw new InvalidOperationException("资产数量超出上限，请缩小扫描目录");
            Array.Sort(guids, StringComparer.Ordinal);
            var directory = Path.Combine(Path.GetDirectoryName(Application.dataPath),
                "Library", "UnityRunBridge", "ui-index-results");
            Directory.CreateDirectory(directory);
            artifact = Path.Combine(directory, handle.JobId + ".jsonl");
            writer = new StreamWriter(artifact + ".pending", false, new UTF8Encoding(false));
        }

        private void ReadAsset(string guid)
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (string.IsNullOrEmpty(path) || !path.StartsWith(root + "/", StringComparison.Ordinal))
                throw new InvalidOperationException("Prefab 在扫描期间已移动或删除");
            if (!path.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase))
            {
                skipped++;
                return;
            }

            string fingerprint = AssetDatabase.GetAssetDependencyHash(path).ToString();
            var row = JsonValue.NewObject();
            row["guid"] = guid;
            row["path"] = path;
            row["fingerprint"] = fingerprint;
            bool changed = !known.TryGetValue(guid, out string previous) || previous != fingerprint;
            known.Remove(guid);
            row["changed"] = changed;
            if (changed)
            {
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if (prefab == null)
                    throw new InvalidOperationException("无法读取 Prefab: " + path);
                JsonValue entries = indexer.ReadControls(prefab);
                foreach (JsonValue entry in entries.Items)
                {
                    if (!entry.TryGetString("localFileId", out _))
                        unidentified++;
                }
                controls += entries.Count;
                row["controls"] = entries;
                scanned++;
            }
            else
                unchanged++;

            string json = JsonWriter.Serialize(row);
            outputBytes += Encoding.UTF8.GetByteCount(json) + 2;
            if (outputBytes > MaxOutputBytes)
                throw new InvalidOperationException("索引产物超过上限，请缩小扫描目录");
            writer.WriteLine(json);
        }

        private void Finish()
        {
            writer.Dispose();
            writer = null;
            File.Move(artifact + ".pending", artifact);
            handle.Succeed(new Dictionary<string, object>
            {
                ["schema"] = Schema,
                ["root"] = root,
                ["artifactPath"] = artifact,
                ["prefabs"] = scanned + unchanged,
                ["scanned"] = scanned,
                ["unchanged"] = unchanged,
                ["skipped"] = skipped,
                ["deleted"] = known.Count,
                ["controlsScanned"] = controls,
                ["unidentifiedScanned"] = unidentified,
                ["durationMs"] = watch.ElapsedMilliseconds,
            });
            Cleanup();
        }

        private void Fail(string code, string message)
        {
            Cleanup();
            handle.Fail(code, message);
        }

        private void Cleanup()
        {
            EditorApplication.update -= Tick;
            AssemblyReloadEvents.beforeAssemblyReload -= Cleanup;
            if (active == this)
                active = null;
            try
            {
                writer?.Dispose();
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            finally
            {
                writer = null;
                if (artifact != null)
                {
                    try { File.Delete(artifact + ".pending"); }
                    catch (IOException) { }
                    catch (UnauthorizedAccessException) { }
                }
            }
        }
    }
}
