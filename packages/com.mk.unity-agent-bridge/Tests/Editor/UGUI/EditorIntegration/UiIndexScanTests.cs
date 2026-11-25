using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEditor;
using UnityEditor.Events;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;
using Object = UnityEngine.Object;

namespace Mk.UnityAgentBridge.Editor.Tests
{
    public sealed class UiIndexScanTests
    {
        private string root;
        private readonly List<string> artifacts = new List<string>();
        private JsonValue last;
        private JsonValue[] rows;

        [SetUp]
        public void SetUp()
        {
            string name = "UiIndexScanTests-" + Guid.NewGuid().ToString("N");
            Assert.IsNotEmpty(AssetDatabase.CreateFolder("Assets", name));
            root = "Assets/" + name;
        }

        [TearDown]
        public void TearDown()
        {
            foreach (string artifact in artifacts)
                File.Delete(artifact);
            artifacts.Clear();
            AssetDatabase.DeleteAsset(root);
        }

        [UnityTest]
        public IEnumerator IndexesPrefabsReadOnlyAndTracksDependenciesAndScopeChanges()
        {
            string sourcePath = root + "/Base.prefab";
            string panelPath = root + "/Panel.prefab";
            string variantPath = root + "/Variant.prefab";
            var source = new GameObject("Action", typeof(RectTransform), typeof(Image), typeof(Button));
            Button button = source.GetComponent<Button>();
            button.interactable = false;
            button.enabled = false;
            button.onClick.AddListener(() => Assert.Fail("Indexer must not invoke any callback"));
            UnityEventTools.AddBoolPersistentListener(button.onClick, source.SetActive, true);
            GameObject baseAsset = PrefabUtility.SaveAsPrefabAsset(source, sourcePath);
            Object.DestroyImmediate(source);
            Assert.IsNotNull(baseAsset);

            var parent = new GameObject("Panel", typeof(RectTransform));
            for (int i = 0; i < 2; i++)
            {
                var nest = (GameObject)PrefabUtility.InstantiatePrefab(baseAsset, parent.transform);
                nest.name = "Duplicate";
            }
            GameObject panelAsset = PrefabUtility.SaveAsPrefabAsset(parent, panelPath);
            Object.DestroyImmediate(parent);
            Assert.IsNotNull(panelAsset);

            var variant = (GameObject)PrefabUtility.InstantiatePrefab(panelAsset);
            variant.transform.GetChild(1).gameObject.SetActive(false);
            Assert.IsNotNull(PrefabUtility.SaveAsPrefabAsset(variant, variantPath));
            Object.DestroyImmediate(variant);
            AssetDatabase.Refresh();
            string[] files = new[] {
                sourcePath, sourcePath + ".meta", panelPath, panelPath + ".meta",
                variantPath, variantPath + ".meta", "Packages/manifest.json", "ProjectSettings/ProjectVersion.txt",
            };
            byte[][] before = files.Select(File.ReadAllBytes).ToArray();

            yield return Scan();
            Assert.AreEqual(3, last["scanned"].AsInt);
            Assert.AreEqual(5, last["controlsScanned"].AsInt);
            Assert.AreEqual(0, last["unidentifiedScanned"].AsInt);
            for (int i = 0; i < files.Length; i++)
                CollectionAssert.AreEqual(before[i], File.ReadAllBytes(files[i]));

            JsonValue[] nested = Asset(panelPath)["controls"].Items.ToArray();
            Assert.AreEqual(2, nested.Length);
            Assert.AreEqual("Duplicate", nested[0]["name"].AsString);
            Assert.AreEqual("Duplicate", nested[1]["name"].AsString);
            Assert.AreEqual(0, nested[0]["path"][0]["siblingIndex"].AsInt);
            Assert.AreEqual(1, nested[1]["path"][0]["siblingIndex"].AsInt);
            foreach (JsonValue control in nested)
            {
                Assert.IsNotEmpty(control["localFileId"].AsString);
                Assert.IsFalse(control["enabled"].AsBoolean);
                Assert.IsFalse(control["interactable"].AsBoolean);
                Assert.AreEqual(1, control["persistentCallbacks"].Count);
                Assert.AreEqual("SetActive", control["persistentCallbacks"][0]["method"].AsString);
            }
            Assert.IsFalse(Asset(variantPath)["controls"][1]["activeSelf"].AsBoolean);

            yield return Scan(Known());
            Assert.AreEqual(0, last["scanned"].AsInt);
            Assert.AreEqual(3, last["unchanged"].AsInt);
            Assert.IsTrue(rows.All(row => !row.TryGet("controls", out _)));
            JsonValue previous = Known();

            var contents = PrefabUtility.LoadPrefabContents(sourcePath);
            try
            {
                contents.GetComponent<Button>().interactable = true;
                PrefabUtility.SaveAsPrefabAsset(contents, sourcePath);
            }
            finally { PrefabUtility.UnloadPrefabContents(contents); }
            AssetDatabase.ImportAsset(sourcePath, ImportAssetOptions.ForceSynchronousImport);
            yield return Scan(previous);
            Assert.AreEqual(3, last["scanned"].AsInt, "基础 Prefab 变化必须使嵌套和 Variant 失效");
            Assert.IsTrue(Asset(variantPath)["controls"][0]["interactable"].AsBoolean);

            previous = Known();
            string panelGuid = Asset(panelPath)["guid"].AsString;
            Assert.AreEqual("", AssetDatabase.MoveAsset(panelPath, root + "/Renamed.prefab"));
            Assert.IsTrue(AssetDatabase.DeleteAsset(variantPath));
            yield return Scan(previous);
            Assert.AreEqual(1, last["deleted"].AsInt);
            Assert.AreEqual(2, last["prefabs"].AsInt);
            Assert.AreEqual(panelGuid, Asset(root + "/Renamed.prefab")["guid"].AsString);
        }

        [Test]
        public void ScanRejectsInvalidRootAndFingerprint()
        {
            RouteHandler route = Route();
            foreach (string request in new[]
                { "{\"root\":\"Assets/../Packages\"}", "{\"root\":\"Packages\"}",
                  "{\"root\":\"Assets\",\"known\":{\"x\":\"bad\"}}" })
            {
                var result = (BridgeResponse)route(BridgeRequestContext.ForTests(rawBody: request));
                Assert.AreEqual("invalid_argument", result.code);
            }
        }

        private static RouteHandler Route()
        {
            RouteHandler route = RouteTable.Resolve("POST", "ui-index/scan", out _);
            Assert.IsNotNull(route);
            return route;
        }

        private IEnumerator Scan(JsonValue known = null)
        {
            var request = JsonValue.NewObject();
            request["root"] = root;
            if (known != null)
                request["known"] = known;
            var response = (JsonValue)Route()(BridgeRequestContext.ForTests(rawBody: JsonWriter.Serialize(request)));
            Assert.IsTrue(response["ok"].AsBoolean);
            string id = response["jobId"].AsString;
            JobRecord job = JobManager.GetJob(id);
            double deadline = EditorApplication.timeSinceStartup + 15;
            while (job.Status == JobStatus.Running && EditorApplication.timeSinceStartup < deadline)
                yield return null;
            Assert.AreEqual(JobStatus.Succeeded, job.Status, job.ErrorCode + ": " + job.ErrorMessage);
            last = JsonParser.Parse(JsonWriter.Serialize(job.Result));
            string artifact = last["artifactPath"].AsString;
            artifacts.Add(artifact);
            Assert.IsTrue(Path.GetFullPath(artifact).Contains("/Library/UnityRunBridge/ui-index-results/")
                || Path.GetFullPath(artifact).Contains("\\Library\\UnityRunBridge\\ui-index-results\\"));
            Assert.IsFalse(File.Exists(artifact + ".pending"));
            rows = File.ReadAllLines(artifact).Select(JsonParser.Parse).ToArray();
        }

        private JsonValue Known()
        {
            var result = JsonValue.NewObject();
            foreach (JsonValue row in rows)
                result[row["guid"].AsString] = row["fingerprint"].AsString;
            return result;
        }

        private JsonValue Asset(string path) => rows.Single(row => row["path"].AsString == path);
    }
}
