using System.Collections;
using System.IO;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Profiling;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEngine.TestTools;

namespace Mk.UnityAgentBridge.Editor.Tests.Profiling
{
    public sealed class ProfilingControllerTests
    {
        [SetUp]
        public void ResetState()
        {
            ProfilingController.ResetForTests();
        }

        [TearDown]
        public void TearDown()
        {
            ProfilingController.ResetForTests();
        }

        [Test]
        public void Routes_AreRegistered()
        {
            Assert.IsNotNull(RouteTable.Resolve("POST", "profiling/start", out _));
            Assert.IsNotNull(RouteTable.Resolve("POST", "profiling/stop", out _));
            Assert.IsNotNull(RouteTable.Resolve("GET", "profiling/status", out _));
        }

        [Test]
        public void CapabilitiesResponse_DeclaresProfilingCapability()
        {
            JsonValue response = CapabilitiesController.BuildResponse();
            bool hasProfiling = false;
            foreach (JsonValue capability in response["capabilities"].Items)
            {
                if (capability.AsString == "profiling")
                {
                    hasProfiling = true;
                }
            }

            Assert.IsTrue(hasProfiling);
        }

        [Test]
        public void Start_NotInPlayMode_ReturnsNotInPlayMode()
        {
            object result = ProfilingController.Start(BridgeRequestContext.ForTests());

            Assert.IsInstanceOf<BridgeResponse>(result);
            Assert.AreEqual("not_in_play_mode", ((BridgeResponse)result).code);
        }

        [Test]
        public void Stop_WhenIdle_ReturnsOkWithNotProfilingCode()
        {
            object result = ProfilingController.Stop(BridgeRequestContext.ForTests());

            Assert.IsInstanceOf<JsonValue>(result);
            JsonValue json = (JsonValue)result;
            Assert.IsTrue(json["ok"].AsBoolean);
            Assert.AreEqual("not_profiling", json["code"].AsString);
            Assert.IsTrue(json["metricsPath"].IsNull);
            Assert.AreEqual(0, json["frameCount"].AsInt);
            Assert.IsFalse(json["interrupted"].AsBoolean);
            Assert.AreEqual(0, json["aggregates"].Count);
        }

        [Test]
        public void Status_WhenIdle_ReturnsProfilingFalse()
        {
            object result = ProfilingController.Status(BridgeRequestContext.ForTests());

            JsonValue json = (JsonValue)result;
            Assert.IsFalse(json["profiling"].AsBoolean);
            Assert.IsFalse(json["interrupted"].AsBoolean);
            Assert.AreEqual(0, json["frameCount"].AsInt);
            Assert.IsTrue(json["metricsPath"].IsNull);
        }

        [UnityTest]
        public IEnumerator StartStopStatus_CoversFullLifecycleInPlayMode()
        {
            // 同 RecordingControllerTests 的约定：EnterPlayMode 触发 domain reload，跨 reload
            // 存活的值必须在 yield return new EnterPlayMode() 之后计算。
            yield return new EnterPlayMode();
            yield return null;

            string projectRoot = ArtifactPathGuard.GetProjectRoot();
            string targetDirectory = Path.Combine(projectRoot, ".unity-agent", "scratch", "profiling-controller-tests");
            if (Directory.Exists(targetDirectory))
            {
                Directory.Delete(targetDirectory, recursive: true);
            }

            try
            {
                // --- start：写出空 metrics.jsonl，状态机进入 profiling ---
                string targetDirectoryJson = targetDirectory.Replace("\\", "\\\\");
                object startResult = ProfilingController.Start(
                    BridgeRequestContext.ForTests(rawBody: $"{{\"targetDirectory\":\"{targetDirectoryJson}\"}}"));

                Assert.IsInstanceOf<JsonValue>(startResult, "start 失败：" + DescribeIfFailure(startResult));
                JsonValue startJson = (JsonValue)startResult;
                Assert.IsTrue(startJson["ok"].AsBoolean);
                Assert.AreEqual(ProfilingController.StateProfiling, ProfilingController.CurrentState());
                Assert.IsTrue(MetricsSampler.IsSampling);

                string metricsPath = startJson["metricsPath"].AsString;
                Assert.IsTrue(File.Exists(metricsPath));
                Assert.AreEqual(string.Empty, File.ReadAllText(metricsPath));
                int unavailableCount = startJson["unavailableMetrics"].Count;

                // 再次 start 应该被拒绝（409 already_profiling）
                object secondStart = ProfilingController.Start(BridgeRequestContext.ForTests());
                Assert.IsInstanceOf<BridgeResponse>(secondStart);
                Assert.AreEqual("already_profiling", ((BridgeResponse)secondStart).code);

                // --- 批量落盘：每 60 帧才 flush 一次，未到阈值时文件应保持为空 ---
                for (int i = 0; i < 59; i++)
                {
                    MetricsSampler.Tick();
                }

                JsonValue statusBeforeFlush = (JsonValue)ProfilingController.Status(BridgeRequestContext.ForTests());
                Assert.AreEqual(59, statusBeforeFlush["frameCount"].AsInt);
                Assert.AreEqual(string.Empty, File.ReadAllText(metricsPath));

                // 第 60 次 tick 触发批量 flush
                MetricsSampler.Tick();
                string[] linesAfterFirstFlush = File.ReadAllLines(metricsPath);
                Assert.AreEqual(60, linesAfterFirstFlush.Length);

                // 再采 3 帧，尚未到下一个 60 的阈值，不会再次 flush
                MetricsSampler.Tick();
                MetricsSampler.Tick();
                MetricsSampler.Tick();
                Assert.AreEqual(60, File.ReadAllLines(metricsPath).Length);

                // --- stop：flush 剩余样本，计算聚合值，回到 idle ---
                object stopResult = ProfilingController.Stop(BridgeRequestContext.ForTests());
                JsonValue stopJson = (JsonValue)stopResult;
                Assert.IsTrue(stopJson["ok"].AsBoolean);
                Assert.AreEqual(63, stopJson["frameCount"].AsInt);
                Assert.IsFalse(stopJson["interrupted"].AsBoolean);
                Assert.AreEqual(ProfilingController.StateIdle, ProfilingController.CurrentState());
                Assert.IsFalse(MetricsSampler.IsSampling);

                Assert.AreEqual(63, File.ReadAllLines(metricsPath).Length);

                JsonValue aggregates = stopJson["aggregates"];
                Assert.AreEqual(7 - unavailableCount, aggregates.Count);
                foreach (string key in aggregates.Keys)
                {
                    JsonValue stat = aggregates[key];
                    Assert.IsTrue(stat.ContainsKey("avg"));
                    Assert.IsTrue(stat.ContainsKey("max"));
                    Assert.IsTrue(stat.ContainsKey("p95"));
                }

                // --- 模拟 domain reload / 退出 Play Mode 打断采样：stop 应如实报告 interrupted ---
                ProfilingController.Start(BridgeRequestContext.ForTests(
                    rawBody: $"{{\"targetDirectory\":\"{targetDirectoryJson}\"}}"));
                ProfilingController.SimulateInterruptionForTests("play_mode_exited");
                Assert.AreEqual(ProfilingController.StateInterrupted, ProfilingController.CurrentState());
                Assert.IsFalse(MetricsSampler.IsSampling);

                JsonValue interruptedStop = (JsonValue)ProfilingController.Stop(BridgeRequestContext.ForTests());
                Assert.IsTrue(interruptedStop["interrupted"].AsBoolean);
            }
            finally
            {
                ProfilingController.ResetForTests();
                if (Directory.Exists(targetDirectory))
                {
                    Directory.Delete(targetDirectory, recursive: true);
                }
            }

            yield return new ExitPlayMode();
        }

        private static string DescribeIfFailure(object result)
        {
            return result is BridgeResponse response ? $"{response.code}: {response.message}" : "n/a";
        }
    }
}
