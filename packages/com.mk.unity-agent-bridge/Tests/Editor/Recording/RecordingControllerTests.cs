using System.Collections;
using System.IO;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Recording;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Tests.Recording
{
    public sealed class RecordingControllerTests
    {
        [SetUp]
        public void ResetState()
        {
            RecordingController.ResetForTests();
        }

        [TearDown]
        public void TearDown()
        {
            RecordingController.ResetForTests();
        }

        [Test]
        public void Routes_AreRegistered()
        {
            Assert.IsNotNull(RouteTable.Resolve("POST", "recording/start", out _));
            Assert.IsNotNull(RouteTable.Resolve("POST", "recording/stop", out _));
            Assert.IsNotNull(RouteTable.Resolve("GET", "recording/status", out _));
        }

        [Test]
        public void CapabilitiesResponse_DeclaresRecordingCapability()
        {
            JsonValue response = CapabilitiesController.BuildResponse();
            bool hasRecording = false;
            foreach (JsonValue capability in response["capabilities"].Items)
            {
                if (capability.AsString == "recording")
                {
                    hasRecording = true;
                }
            }

            Assert.IsTrue(hasRecording);
        }

        [Test]
        public void Start_NotInPlayMode_ReturnsNotInPlayMode()
        {
            object result = RecordingController.Start(BridgeRequestContext.ForTests());

            Assert.IsInstanceOf<BridgeResponse>(result);
            Assert.AreEqual("not_in_play_mode", ((BridgeResponse)result).code);
        }

        [Test]
        public void Stop_WhenIdle_ReturnsOkWithNotRecordingCode()
        {
            object result = RecordingController.Stop(BridgeRequestContext.ForTests());

            Assert.IsInstanceOf<JsonValue>(result);
            JsonValue json = (JsonValue)result;
            Assert.IsTrue(json["ok"].AsBoolean);
            Assert.AreEqual("not_recording", json["code"].AsString);
            Assert.IsTrue(json["actionsPath"].IsNull);
            Assert.AreEqual(0, json["actionCount"].AsInt);
            Assert.IsFalse(json["interrupted"].AsBoolean);
        }

        [Test]
        public void Status_WhenIdle_ReturnsRecordingFalse()
        {
            object result = RecordingController.Status(BridgeRequestContext.ForTests());

            JsonValue json = (JsonValue)result;
            Assert.IsFalse(json["recording"].AsBoolean);
            Assert.IsFalse(json["interrupted"].AsBoolean);
            Assert.AreEqual(0, json["actionCount"].AsInt);
            Assert.IsTrue(json["actionsPath"].IsNull);
        }

        [UnityTest]
        public IEnumerator StartStopStatus_CoversFullLifecycleInPlayMode()
        {
            // 注意：entering Play Mode 默认会触发 domain reload，这个 UnityTest 协程的状态机实例
            // 会被丢弃重建，reload 之前赋值的局部变量在 resume 后一律变回默认值（string 为 null）。
            // 因此所有需要跨 EnterPlayMode 存活的值都必须在 yield return new EnterPlayMode() 之后计算，
            // 不能像普通协程那样想当然地在前面准备好（同 PointerSimulatorTests/InputSimulatorTests 的约定）。
            yield return new EnterPlayMode();
            yield return null;

            string projectRoot = ArtifactPathGuard.GetProjectRoot();
            string targetDirectory = Path.Combine(projectRoot, ".unity-agent", "scratch", "recording-controller-tests");
            if (Directory.Exists(targetDirectory))
            {
                Directory.Delete(targetDirectory, recursive: true);
            }

            GameObject eventSystemGo = null;
            GameObject canvasGo = null;

            try
            {
                eventSystemGo = new GameObject("RecordingControllerTests_EventSystem");
                eventSystemGo.AddComponent<EventSystem>();

                canvasGo = new GameObject("RecordingControllerTests_Canvas");
                Canvas canvas = canvasGo.AddComponent<Canvas>();
                canvas.renderMode = RenderMode.ScreenSpaceOverlay;
                canvasGo.AddComponent<GraphicRaycaster>();

                GameObject buttonGo = new GameObject("RecordingControllerTests_Button", typeof(RectTransform));
                buttonGo.transform.SetParent(canvas.transform, worldPositionStays: false);
                RectTransform rect = (RectTransform)buttonGo.transform;
                rect.anchorMin = Vector2.zero;
                rect.anchorMax = Vector2.zero;
                rect.pivot = Vector2.zero;
                rect.anchoredPosition = new Vector2(100, 100);
                rect.sizeDelta = new Vector2(200, 60);
                buttonGo.AddComponent<Image>().raycastTarget = true;
                buttonGo.AddComponent<Button>();

                yield return null;

                // --- start：写出 meta + 空 actions 文件，状态机进入 recording ---
                string targetDirectoryJson = targetDirectory.Replace("\\", "\\\\");
                object startResult = RecordingController.Start(
                    BridgeRequestContext.ForTests(rawBody: $"{{\"targetDirectory\":\"{targetDirectoryJson}\"}}"));

                Assert.IsInstanceOf<JsonValue>(startResult, "start 失败：" + DescribeIfFailure(startResult));
                JsonValue startJson = (JsonValue)startResult;
                Assert.IsTrue(startJson["ok"].AsBoolean);
                Assert.AreEqual(RecordingController.StateRecording, RecordingController.CurrentState());
                Assert.IsTrue(RecordingListener.IsListening);

                string actionsPath = startJson["actionsPath"].AsString;
                string metaPath = startJson["metaPath"].AsString;
                Assert.IsTrue(File.Exists(actionsPath));
                Assert.IsTrue(File.Exists(metaPath));
                Assert.AreEqual(string.Empty, File.ReadAllText(actionsPath));

                JsonValue meta = JsonParser.Parse(File.ReadAllText(metaPath));
                Assert.AreEqual(1, meta["schemaVersion"].AsLong);
                Assert.IsFalse(meta["activeScene"].IsNull);

                // 再次 start 应该被拒绝（409 already_recording）
                object secondStart = RecordingController.Start(BridgeRequestContext.ForTests());
                Assert.IsInstanceOf<BridgeResponse>(secondStart);
                Assert.AreEqual("already_recording", ((BridgeResponse)secondStart).code);

                // --- 通过真实的点击解析路径产生一次 click 动作，覆盖落盘 + actionCount 递增 ---
                Vector2 insideButton = new Vector2(150, 130);
                RecordingListener.ProcessPointerDown(insideButton);
                RecordingListener.ProcessPointerUp(insideButton);

                JsonValue statusJson = (JsonValue)RecordingController.Status(BridgeRequestContext.ForTests());
                Assert.IsTrue(statusJson["recording"].AsBoolean);
                Assert.AreEqual(1, statusJson["actionCount"].AsInt);

                // --- stop：停止监听，返回累计 actionCount，回到 idle ---
                object stopResult = RecordingController.Stop(BridgeRequestContext.ForTests());
                JsonValue stopJson = (JsonValue)stopResult;
                Assert.IsTrue(stopJson["ok"].AsBoolean);
                Assert.AreEqual(1, stopJson["actionCount"].AsInt);
                Assert.IsFalse(stopJson["interrupted"].AsBoolean);
                Assert.AreEqual(RecordingController.StateIdle, RecordingController.CurrentState());
                Assert.IsFalse(RecordingListener.IsListening);

                string actionsContent = File.ReadAllText(actionsPath);
                StringAssert.Contains("\"type\":\"click\"", actionsContent);
                StringAssert.Contains("\"path\":\"RecordingControllerTests_Canvas/RecordingControllerTests_Button\"", actionsContent);

                // --- 模拟 domain reload / 退出 Play Mode 打断录制：stop 应如实报告 interrupted ---
                RecordingController.Start(BridgeRequestContext.ForTests(
                    rawBody: $"{{\"targetDirectory\":\"{targetDirectoryJson}\"}}"));
                RecordingController.SimulateInterruptionForTests("play_mode_exited");
                Assert.AreEqual(RecordingController.StateInterrupted, RecordingController.CurrentState());
                Assert.IsFalse(RecordingListener.IsListening);

                JsonValue interruptedStop = (JsonValue)RecordingController.Stop(BridgeRequestContext.ForTests());
                Assert.IsTrue(interruptedStop["interrupted"].AsBoolean);
            }
            finally
            {
                RecordingController.ResetForTests();
                if (eventSystemGo != null) Object.DestroyImmediate(eventSystemGo);
                if (canvasGo != null) Object.DestroyImmediate(canvasGo);
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
