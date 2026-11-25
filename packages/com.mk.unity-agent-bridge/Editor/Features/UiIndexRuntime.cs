using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Text.RegularExpressions;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Interaction;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Mk.UnityAgentBridge.Editor
{
    [InitializeOnLoad]
    internal static class UiIndexRuntime
    {
        private static readonly Regex Hash = new Regex("^[0-9a-f]{32}$");
        private static readonly Regex Id = new Regex("^[0-9a-f]{64}$");
        private static readonly Dictionary<string, Witness> Witnesses = new Dictionary<string, Witness>();
        private const int MaxWitnesses = 128;
        private const string ActionName = "ui-index-click";
        private const string EditBindings = "Mk.UnityAgentBridge.UiIndex.EditBindings";
        private const string PlayBindings = "Mk.UnityAgentBridge.UiIndex.PlayBindings";
        private static JsonValue playBindingCache;

        private sealed class Witness
        {
            public Component Component;
            public string Path;
            public int SceneHandle;
            public double ExpiresAt;
        }

        static UiIndexRuntime()
        {
            EditorApplication.playModeStateChanged += state =>
            {
                Witnesses.Clear();
                playBindingCache = null;
                if (state == PlayModeStateChange.ExitingEditMode)
                    PromoteSavedBindings();
                else if (state == PlayModeStateChange.EnteredEditMode)
                    SessionState.EraseString(PlayBindings);
            };
        }

        internal static object Bind(BridgeRequestContext ctx)
        {
            JsonValue body = ctx.Body;
            string scenePath = body?.GetString("scene");
            if (body == null || !body.IsObject || !Bounded(scenePath) ||
                !scenePath.EndsWith(".unity", StringComparison.OrdinalIgnoreCase) || body.GetString("binding") != "prefab")
                return Failure("invalid_argument", "绑定需要保存过的场景路径和静态 Prefab 控件");
            if (EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isCompiling || EditorApplication.isUpdating)
                return Failure("editor_not_ready", "仅空闲编辑模式允许绑定场景中的 Prefab");
            if (!FindScene(scenePath, out Scene scene, out bool ambiguous) || scene.isDirty)
                return Failure(ambiguous ? "ui_index_ambiguous" : "ui_index_scene_missing", "请先打开已保存、未修改的场景");
            if (!TryResolvePrefab(body, scene, true, out Component target, out BridgeResponse error))
                return error;
            if (!ResolveUniqueRoot(scene, body.GetString("instanceRoot"), out Transform instance, out _)
                || !TrySceneId(instance.gameObject, scene.path, out GlobalObjectId root)
                || !TrySceneId(target, scene.path, out GlobalObjectId part))
                return Failure("ui_index_source_mismatch", "Unity 没有为场景实例提供可复验的持久身份");

            JsonValue bindings = LoadBindings(EditBindings);
            string key = WitnessKey(body);
            if (bindings.Count >= 256 && !bindings.ContainsKey(key))
                return Failure("ui_index_busy", "已达到 Editor 绑定上限；可重启 Editor 清空临时绑定");
            var record = JsonValue.NewObject();
            record["scene"] = scene.path;
            record["sceneFingerprint"] = AssetDatabase.GetAssetDependencyHash(scene.path).ToString();
            record["fingerprint"] = body.GetString("fingerprint");
            // Unity 2022.3 serializes scene-local prefab objects in Play as
            // targetObjectId XOR targetPrefabId. Only use this bridge if both object
            // IDs also round trip through Unity and keep the same scene GUID.
            record["rootId"] = Normalized(root).ToString(CultureInfo.InvariantCulture);
            record["componentId"] = Normalized(part).ToString(CultureInfo.InvariantCulture);
            bindings[key] = record;
            SessionState.SetString(EditBindings, bindings.ToString());

            var response = JsonValue.NewObject();
            response["ok"] = true;
            response["bound"] = true;
            response["scene"] = scene.path;
            response["controlId"] = body.GetString("controlId");
            response["liveVerified"] = false;
            return response;
        }

        private static JsonValue LoadBindings(string key)
        {
            string json = SessionState.GetString(key, "{}");
            return JsonParser.TryParse(json, out JsonValue value, out _) && value.IsObject
                ? value : JsonValue.NewObject();
        }

        private static void PromoteSavedBindings()
        {
            var selected = JsonValue.NewObject();
            SessionState.EraseString(PlayBindings);
            var sceneHashes = new Dictionary<string, string>();
            foreach (var entry in LoadBindings(EditBindings).Properties)
            {
                var record = entry.Value;
                string path = record.GetString("scene");
                if (string.IsNullOrEmpty(path))
                    continue;
                if (!sceneHashes.TryGetValue(path, out string hash))
                {
                    hash = FindScene(path, out Scene scene, out _) && !scene.isDirty
                        ? AssetDatabase.GetAssetDependencyHash(scene.path).ToString() : null;
                    sceneHashes[path] = hash;
                }
                if (hash != null && record.GetString("sceneFingerprint") == hash)
                    selected[entry.Key] = record;
            }
            SessionState.SetString(PlayBindings, selected.ToString());
        }

        private static string WitnessKey(JsonValue request) => string.Join("\n",
            request.GetString("scene"), request.GetString("instanceRoot"), request.GetString("controlId"));

        private static ulong Normalized(GlobalObjectId id) => id.targetObjectId ^ id.targetPrefabId;

        private static bool TrySceneId(UnityEngine.Object target, string scenePath, out GlobalObjectId id)
        {
            id = GlobalObjectId.GetGlobalObjectIdSlow(target);
            return id.identifierType == 2 && Normalized(id) != 0
                && id.assetGUID.ToString() == AssetDatabase.AssetPathToGUID(scenePath)
                && GlobalObjectId.GlobalObjectIdentifierToObjectSlow(id) == target;
        }

        private static bool CheckBinding(JsonValue body, Scene scene, GameObject root, Component target)
        {
            playBindingCache ??= LoadBindings(PlayBindings);
            return playBindingCache.TryGetObject(WitnessKey(body), out JsonValue binding)
                && binding.GetString("fingerprint") == body.GetString("fingerprint")
                && binding.GetString("sceneFingerprint") == AssetDatabase.GetAssetDependencyHash(scene.path).ToString()
                && TrySceneId(root, scene.path, out GlobalObjectId rootId)
                && TrySceneId(target, scene.path, out GlobalObjectId partId)
                && binding.GetString("rootId") == Normalized(rootId).ToString(CultureInfo.InvariantCulture)
                && binding.GetString("componentId") == Normalized(partId).ToString(CultureInfo.InvariantCulture);
        }

        internal static object Execute(BridgeRequestContext ctx, IIndexedClickBackend backend, bool click)
        {
            var watch = Stopwatch.StartNew();
            JsonValue body = ctx.Body;
            string scene = body?.GetString("scene");
            var request = JsonValue.NewObject();
            foreach (string key in new[] { "controlId", "instanceRoot", "runtimePath", "assetGuid" })
            {
                string value = body?.GetString(key);
                if (!string.IsNullOrEmpty(value) && value.Length <= 1024)
                    request[key] = value;
            }
            if (body?.GetString("binding") == "runtime")
                request["binding"] = "runtime";
            object result = Failure("internal_error", "运行态定位未完成");
            try
            {
                result = ExecuteCore(body, scene, backend, click);
            }
            catch (Exception)
            {
                result = Failure("internal_error", "运行态定位或派发异常；请观察界面，不要盲目重试");
            }
            finally
            {
                if (click)
                    InteractionAuditLog.AppendFromResponse(ActionName, request, Bounded(scene) ? scene : null,
                        result, watch.ElapsedMilliseconds);
            }
            return result;
        }

        private static object ExecuteCore(JsonValue body, string scenePath, IIndexedClickBackend backend, bool click)
        {
            if (body == null || !body.IsObject || !Bounded(scenePath)
                || !scenePath.EndsWith(".unity", StringComparison.OrdinalIgnoreCase))
                return Failure("invalid_argument", "需要完整且明确的已保存场景路径");
            if (!EditorApplication.isPlaying || !EditorApplication.isPlayingOrWillChangePlaymode)
                return Failure("not_in_play_mode", "索引运行态定位与点击要求 Play Mode");
            if (!FindScene(scenePath, out Scene scene, out bool ambiguous))
                return Failure(ambiguous ? "ui_index_ambiguous" : "ui_index_scene_missing", "无法唯一匹配已加载场景");

            Component expected;
            string binding = body.GetString("binding");
            switch (binding)
            {
                case "prefab":
                    if (!TryResolvePrefab(body, scene, false, out expected, out BridgeResponse error))
                        return error;
                    break;
                case "runtime":
                    return ExecuteRuntimeWitness(body, scene, backend, click);
                default:
                    return Failure("invalid_argument", "需要 prefab 或 runtime 绑定");
            }

            if (backend.UniqueClickHandler(expected.gameObject) != expected)
                return Failure("ui_index_handler_mismatch", "目标未激活、组件禁用或同节点点击处理器不唯一");
            return Respond(expected, scenePath, binding, backend, click);
        }

        private static object ExecuteRuntimeWitness(JsonValue body, Scene scene, IIndexedClickBackend backend, bool click)
        {
            double now = EditorApplication.timeSinceStartup;
            var expired = new List<string>();
            foreach (var pair in Witnesses)
            {
                if (pair.Value.ExpiresAt < now || pair.Value.Component == null)
                    expired.Add(pair.Key);
            }
            foreach (string key in expired)
                Witnesses.Remove(key);

            if (click)
            {
                string token = body.GetString("runtimeToken");
                if (token == null || !Witnesses.TryGetValue(token, out Witness witness))
                    return Failure("ui_index_witness_expired", "当前 Play Mode 没有有效运行态凭证，请重新观察并 resolve");
                Witnesses.Remove(token);
                Component target = witness.Component;
                if (target == null || witness.SceneHandle != scene.handle || target.gameObject.scene.handle != scene.handle
                    || NodePath.BuildPath(target.transform) != witness.Path || backend.UniqueClickHandler(target.gameObject) != target)
                    return Failure("ui_index_stale", "运行态目标或场景已发生变化");
                return Respond(target, scene.path, "runtime", backend, true);
            }

            string path = body.GetString("runtimePath");
            if (!Bounded(path) || !body.TryGetLong("instanceId", out long id) || id == 0 || id < int.MinValue || id > int.MaxValue)
                return Failure("invalid_argument", "动态控件需要当前 Hierarchy 观测的路径和 instanceId");
            GameObject node = EditorUtility.InstanceIDToObject((int)id) as GameObject;
            if (node == null || node.scene.handle != scene.handle || NodePath.BuildPath(node.transform) != path)
                return Failure("ui_index_stale", "当前路径或场景与所观察实例不符");
            Component expected = backend.UniqueClickHandler(node);
            if (expected == null)
                return Failure("ui_index_handler_mismatch", "动态节点没有唯一激活的点击处理器");
            if (Witnesses.Count >= MaxWitnesses)
                return Failure("ui_index_busy", "运行态凭证过多，请使用有效凭证或稍后重新解析");

            var response = (JsonValue)Respond(expected, scene.path, "runtime", backend, false);
            string witnessId = Guid.NewGuid().ToString("N");
            Witnesses.Add(witnessId, new Witness { Component = expected, Path = path,
                SceneHandle = scene.handle, ExpiresAt = now + 120 });
            response["runtimeToken"] = witnessId;
            response["expiresInSeconds"] = 120;
            return response;
        }

        private static object Respond(Component component, string scene, string binding, IIndexedClickBackend backend, bool click)
        {
            var response = JsonValue.NewObject();
            response["ok"] = true;
            response["scene"] = scene;
            response["binding"] = binding;
            string path = NodePath.BuildPath(component.transform);
            response["resolvedPath"] = path;
            response["instanceId"] = component.gameObject.GetInstanceID();
            response["componentType"] = component.GetType().FullName;
            response["liveVerified"] = true;
            if (!click)
            {
                response["clickabilityVerified"] = false;
                return response;
            }

            int width = Screen.width;
            int height = Screen.height;
            InteractionOperationResult dispatched = backend.ClickIndexed(component);
            if (!dispatched.Ok)
            {
                var failure = JsonValue.NewObject();
                failure["ok"] = false;
                failure["code"] = dispatched.ErrorCode;
                failure["message"] = dispatched.ErrorMessage;
                if (dispatched.ErrorCode == "occluded" && dispatched.RaycastHit != null)
                    failure["blockedBy"] = NodePath.BuildPath(dispatched.RaycastHit.transform);
                return failure;
            }
            response["clicked"] = path;
            response["raycastHit"] = dispatched.RaycastHit != null ? NodePath.BuildPath(dispatched.RaycastHit.transform) : null;
            response["forced"] = false;
            response["clickabilityVerified"] = true;
            var events = JsonValue.NewArray();
            foreach (string @event in dispatched.Events)
                events.Add(@event);
            response["events"] = events;
            if (dispatched.ScreenPoint is Vector2 point)
            {
                var screen = JsonValue.NewObject();
                screen["x"] = point.x;
                screen["y"] = point.y;
                screen["width"] = width;
                screen["height"] = height;
                response["screenPoint"] = screen;
            }
            return response;
        }

        private static bool TryResolvePrefab(JsonValue body, Scene scene, bool editProof,
            out Component expected, out BridgeResponse error)
        {
            expected = null;
            string guid = body.GetString("assetGuid");
            string fingerprint = body.GetString("fingerprint");
            string sourceGuid = body.GetString("sourceGuid");
            string localFileId = body.GetString("localFileId");
            string assetPath = body.GetString("assetPath");
            string rootPath = body.GetString("instanceRoot");
            string kind = body.GetString("componentType");
            if (!IsHash(guid) || !IsHash(fingerprint) || !IsHash(sourceGuid) || !Bounded(assetPath)
                || !Bounded(rootPath) || !Bounded(kind) || !Id.IsMatch(body.GetString("controlId", ""))
                || !body.TryGetArray("relativePath", out JsonValue steps) || steps.Count > 128
                || !body.TryGetLong("componentIndex", out long slot) || slot < 0 || slot > 4096
                || !long.TryParse(localFileId, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out long localId)
                || localId == 0)
            {
                error = Failure("invalid_argument", "静态控件缺少可核验的资产、实例根或组件身份");
                return false;
            }

            string currentAsset = AssetDatabase.GUIDToAssetPath(guid);
            if (currentAsset != assetPath || !currentAsset.StartsWith("Assets/", StringComparison.Ordinal)
                || !currentAsset.EndsWith(".prefab", StringComparison.OrdinalIgnoreCase)
                || AssetDatabase.GetAssetDependencyHash(currentAsset).ToString() != fingerprint)
            {
                error = Failure("ui_index_stale", "Prefab 路径或依赖指纹已变化，请重新同步");
                return false;
            }

            if (!ResolveUniqueRoot(scene, rootPath, out Transform runtime, out bool ambiguous))
            {
                error = Failure(ambiguous ? "ui_index_ambiguous" : "ui_index_target_missing", "运行态实例根路径未唯一匹配");
                return false;
            }

            var asset = AssetDatabase.LoadAssetAtPath<GameObject>(currentAsset);
            if (asset == null)
            {
                error = Failure("ui_index_source_mismatch", "Prefab 无法读取");
                return false;
            }
            GameObject instanceRoot = runtime.gameObject;

            Transform source = asset.transform;
            foreach (JsonValue step in steps.Items)
            {
                if (!step.IsObject || !step.TryGetString("name", out string name)
                    || !step.TryGetLong("siblingIndex", out long index) || index < 0
                    || index >= runtime.childCount || index >= source.childCount)
                {
                    error = Failure("ui_index_stale", "Prefab 或实例结构已经变化");
                    return false;
                }
                source = source.GetChild((int)index);
                runtime = runtime.GetChild((int)index);
                if (source.name != name || runtime.name != name)
                {
                    error = Failure("ui_index_stale", "子节点名称或排序已经变化");
                    return false;
                }
            }

            Component[] templateParts = source.GetComponents<Component>();
            Component[] liveParts = runtime.GetComponents<Component>();
            if (slot >= templateParts.Length || slot >= liveParts.Length)
            {
                error = Failure("ui_index_stale", "组件槽位已经变化");
                return false;
            }
            Component template = templateParts[(int)slot];
            Component actual = liveParts[(int)slot];
            if (template == null || actual == null || template.GetType().FullName != kind || actual.GetType() != template.GetType()
                || !AssetDatabase.TryGetGUIDAndLocalFileIdentifier(template, out string actualGuid, out long actualId)
                || actualGuid != sourceGuid || actualId != localId)
            {
                error = Failure("ui_index_source_mismatch", "实际组件来源与缓存身份不匹配");
                return false;
            }
            bool directSource = PrefabUtility.GetCorrespondingObjectFromSourceAtPath(instanceRoot, currentAsset) == asset
                && PrefabUtility.GetCorrespondingObjectFromSourceAtPath(actual, currentAsset) == template;
            if (!directSource && (editProof || !CheckBinding(body, scene, instanceRoot, actual)))
            {
                error = Failure("ui_index_source_mismatch",
                    "无法证明此组件来自目标 Prefab；请在 Edit Mode 绑定已保存场景，或观察动态实例后使用运行态凭证");
                return false;
            }
            expected = actual;
            error = null;
            return true;
        }

        private static bool ResolveUniqueRoot(Scene scene, string path, out Transform node, out bool ambiguous)
        {
            node = null;
            ambiguous = false;
            foreach (string name in path.Split('/'))
            {
                if (!Bounded(name))
                    return false;
                Transform found = null;
                if (node == null)
                {
                    foreach (GameObject candidate in scene.GetRootGameObjects())
                    {
                        if (candidate.name != name)
                            continue;
                        if (found != null)
                        {
                            ambiguous = true;
                            return false;
                        }
                        found = candidate.transform;
                    }
                }
                else
                {
                    foreach (Transform candidate in node)
                    {
                        if (candidate.name != name)
                            continue;
                        if (found != null)
                        {
                            ambiguous = true;
                            return false;
                        }
                        found = candidate;
                    }
                }
                if (found == null)
                    return false;
                node = found;
            }
            return node != null;
        }

        private static bool FindScene(string path, out Scene scene, out bool ambiguous)
        {
            scene = default;
            ambiguous = false;
            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                Scene candidate = SceneManager.GetSceneAt(i);
                if (!candidate.isLoaded || candidate.path != path)
                    continue;
                if (scene.IsValid())
                {
                    ambiguous = true;
                    return false;
                }
                scene = candidate;
            }
            return scene.IsValid();
        }

        private static bool Bounded(string value) => !string.IsNullOrWhiteSpace(value) && value.Length <= 1024;
        private static bool IsHash(string value) => value != null && Hash.IsMatch(value);
        private static BridgeResponse Failure(string code, string message) => BridgeResponse.Failure(code, message);
    }
}
