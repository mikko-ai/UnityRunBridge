using System.Collections.Generic;
using System.IO;
using Mk.UnityAgentBridge.Editor.Health;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Tests.Health
{
    public sealed class PrefabScanRunnerTests
    {
        private const string TempAssetDir = "Assets/UnityAgentBridgeTests_PrefabScan";

        private readonly List<GameObject> spawned = new List<GameObject>();

        [SetUp]
        public void ResetState()
        {
            PrefabScanRunner.ResetForTests();
            JobManager.CompleteAllRunningForTests("test_reset");
        }

        [TearDown]
        public void TearDown()
        {
            PrefabScanRunner.ResetForTests();
            JobManager.CompleteAllRunningForTests("test_reset");

            foreach (GameObject go in spawned)
            {
                if (go != null)
                {
                    Object.DestroyImmediate(go);
                }
            }

            spawned.Clear();

            if (AssetDatabase.IsValidFolder(TempAssetDir))
            {
                AssetDatabase.DeleteAsset(TempAssetDir);
            }
        }

        private static List<string> FakePaths(int count)
        {
            List<string> paths = new List<string>(count);
            for (int i = 0; i < count; i++)
            {
                // 不存在的路径：ScanOne 里 LoadAssetAtPath 会返回 null 并被跳过，
                // 专门用来测试批处理数量而不受测试项目里真实 Prefab 数量的影响。
                paths.Add($"Assets/DoesNotExist/Fake_{i}.prefab");
            }

            return paths;
        }

        [Test]
        public void Tick_ProcessesAtMostBatchSizePerCall()
        {
            List<string> paths = FakePaths(PrefabScanRunner.BatchSize * 2 + 20);
            JobStartResult start = JobManager.StartJob("scan-prefabs-test", handle =>
            {
                PrefabScanRunner.StartWithPaths(handle, paths);
            });

            Assert.IsTrue(start.Ok);
            Assert.IsTrue(PrefabScanRunner.IsRunning);
            Assert.AreEqual(paths.Count, PrefabScanRunner.PendingCount);

            PrefabScanRunner.Tick();
            Assert.AreEqual(paths.Count - PrefabScanRunner.BatchSize, PrefabScanRunner.PendingCount);
            Assert.IsTrue(PrefabScanRunner.IsRunning, "还没扫完，job 不应该提前完成");

            PrefabScanRunner.Tick();
            Assert.AreEqual(paths.Count - (2 * PrefabScanRunner.BatchSize), PrefabScanRunner.PendingCount);
            Assert.IsTrue(PrefabScanRunner.IsRunning);

            PrefabScanRunner.Tick();
            Assert.AreEqual(0, PrefabScanRunner.PendingCount);
            Assert.IsFalse(PrefabScanRunner.IsRunning, "剩余不足一个 batch 时应该在这次 tick 里扫完并结束");

            JobRecordSnapshot snapshot = GetJobSnapshot(start.JobId);
            Assert.AreEqual("succeeded", snapshot.Status);
            Assert.AreEqual(paths.Count, snapshot.Result["scannedCount"].AsInt);
            Assert.AreEqual(0, snapshot.Result["assetsWithMissingScripts"].Count);
        }

        [Test]
        public void StartWithPaths_WhileAlreadyRunning_IsIgnoredAndDoesNotCorruptFirstScan()
        {
            List<string> firstPaths = FakePaths(3);
            JobStartResult first = JobManager.StartJob("scan-prefabs-test", handle =>
            {
                PrefabScanRunner.StartWithPaths(handle, firstPaths);
            });
            Assert.IsTrue(PrefabScanRunner.IsRunning);
            Assert.AreEqual(3, PrefabScanRunner.PendingCount);

            // 模拟第二次并发调用（例如同一 tick 内两次 POST /health/scan-prefabs）：
            // 不应覆盖第一次的 pendingPaths/activeHandle，也不应重复订阅 EditorApplication.update。
            List<string> secondPaths = FakePaths(10);
            JobStartResult second = JobManager.StartJob("scan-prefabs-test", handle =>
            {
                PrefabScanRunner.StartWithPaths(handle, secondPaths);
            });

            Assert.AreEqual(3, PrefabScanRunner.PendingCount, "第二次调用不应覆盖第一次仍在进行的扫描状态");

            PrefabScanRunner.Tick();

            Assert.AreEqual(0, PrefabScanRunner.PendingCount);
            Assert.IsFalse(PrefabScanRunner.IsRunning);

            JobRecordSnapshot firstSnapshot = GetJobSnapshot(first.JobId);
            Assert.AreEqual("succeeded", firstSnapshot.Status, "第一个 job 必须正常完成，不能被第二次调用悬空");
            Assert.AreEqual(3, firstSnapshot.Result["scannedCount"].AsInt);

            // 第二次调用被 StartWithPaths 直接忽略，从未真正开始，job 会一直停留在 running
            // 直到测试 TearDown 里 CompleteAllRunningForTests 收尾——这里只需确认它没有意外成功。
            JsonValue secondResponse = JobManager.BuildJobResponse(JobManager.GetJob(second.JobId));
            Assert.AreEqual("running", secondResponse["job"]["status"].AsString);
        }

        [Test]
        public void Tick_NonExistentAssetPaths_AreSkippedWithoutError()
        {
            List<string> paths = FakePaths(3);
            JobStartResult start = JobManager.StartJob("scan-prefabs-test", handle =>
            {
                PrefabScanRunner.StartWithPaths(handle, paths);
            });

            PrefabScanRunner.Tick();

            JobRecordSnapshot snapshot = GetJobSnapshot(start.JobId);
            Assert.AreEqual("succeeded", snapshot.Status);
            Assert.AreEqual(3, snapshot.Result["scannedCount"].AsInt);
            Assert.AreEqual(0, snapshot.Result["assetsWithMissingScripts"].Count);
        }

        [Test]
        public void Tick_CleanPrefabWithoutMissingScript_IsNotFlagged()
        {
            AssetDatabase.CreateFolder("Assets", "UnityAgentBridgeTests_PrefabScan");
            GameObject source = new GameObject("CleanPrefabSource");
            spawned.Add(source);
            string path = $"{TempAssetDir}/Clean.prefab";
            PrefabUtility.SaveAsPrefabAsset(source, path);

            JobStartResult start = JobManager.StartJob("scan-prefabs-test", handle =>
            {
                PrefabScanRunner.StartWithPaths(handle, new List<string> { path });
            });
            PrefabScanRunner.Tick();

            JobRecordSnapshot snapshot = GetJobSnapshot(start.JobId);
            Assert.AreEqual("succeeded", snapshot.Status);
            Assert.AreEqual(0, snapshot.Result["assetsWithMissingScripts"].Count);
        }

        [Test]
        public void Tick_PrefabWithMissingScript_IsFlaggedByPath()
        {
            AssetDatabase.CreateFolder("Assets", "UnityAgentBridgeTests_PrefabScan");
            string path = $"{TempAssetDir}/MissingScript.prefab";
            string projectRoot = Directory.GetParent(Application.dataPath).FullName;
            File.WriteAllText(Path.Combine(projectRoot, path), MissingScriptPrefabYaml);
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);

            JobStartResult start = JobManager.StartJob("scan-prefabs-test", handle =>
            {
                PrefabScanRunner.StartWithPaths(handle, new List<string> { path });
            });
            PrefabScanRunner.Tick();

            JobRecordSnapshot snapshot = GetJobSnapshot(start.JobId);
            Assert.AreEqual("succeeded", snapshot.Status);
            Assert.AreEqual(1, snapshot.Result["assetsWithMissingScripts"].Count);
            Assert.AreEqual(path, snapshot.Result["assetsWithMissingScripts"][0].AsString);
        }

        private static JobRecordSnapshot GetJobSnapshot(string jobId)
        {
            JsonValue response = JobManager.BuildJobResponse(JobManager.GetJob(jobId));
            JsonValue job = response["job"];
            return new JobRecordSnapshot(job["status"].AsString, job["result"]);
        }

        private readonly struct JobRecordSnapshot
        {
            public JobRecordSnapshot(string status, JsonValue result)
            {
                Status = status;
                Result = result;
            }

            public string Status { get; }
            public JsonValue Result { get; }
        }

        // 手工构造的最小可用 Prefab YAML：一个 GameObject + Transform + 引用不存在 guid 的
        // MonoBehaviour（m_Script 指向的脚本在项目里找不到），Unity 加载后该组件的 GetComponents
        // 结果里会是 null，也就是 NodeSerializer.HasMissingScript 检测的目标场景。
        private const string MissingScriptPrefabYaml = @"%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100000
GameObject:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  serializedVersion: 6
  m_Component:
  - component: {fileID: 400000}
  - component: {fileID: 114000}
  m_Layer: 0
  m_Name: MissingScriptHolder
  m_TagString: Untagged
  m_Icon: {fileID: 0}
  m_NavMeshLayer: 0
  m_StaticEditorFlags: 0
  m_IsActive: 1
--- !u!4 &400000
Transform:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_GameObject: {fileID: 100000}
  serializedVersion: 2
  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
  m_LocalPosition: {x: 0, y: 0, z: 0}
  m_LocalScale: {x: 1, y: 1, z: 1}
  m_ConstrainProportionsScale: 0
  m_Children: []
  m_Father: {fileID: 0}
  m_RootOrder: 0
  m_LocalEulerAnglesHint: {x: 0, y: 0, z: 0}
--- !u!114 &114000
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_GameObject: {fileID: 100000}
  m_Enabled: 1
  m_EditorHideFlags: 0
  m_Script: {fileID: 11500000, guid: 0123456789abcdef0123456789abcdef, type: 3}
  m_Name: 
  m_EditorClassIdentifier: 
";
    }
}
