using System.Collections;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Interaction;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Tests.Interaction
{
    /// <summary>
    /// long-press / drag 跨帧手势 EditorIntegration：共用一次 Play Mode，覆盖事件顺序、
    /// duration、delta、遮挡、single-flight、取消清理与 click 回归。
    /// </summary>
    public sealed class InteractionGestureRunnerTests
    {
        private static GameObject Spawn(string name, Transform parent = null)
        {
            GameObject go = new GameObject(name);
            if (parent != null)
            {
                go.transform.SetParent(parent, worldPositionStays: false);
            }

            return go;
        }

        private static EventSystem CreateEventSystem()
        {
            return Spawn("GestureTests_EventSystem").AddComponent<EventSystem>();
        }

        private static Canvas CreateOverlayCanvas()
        {
            GameObject go = Spawn("GestureTests_Canvas");
            Canvas canvas = go.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            go.AddComponent<GraphicRaycaster>();
            return canvas;
        }

        private static Button CreateButton(Transform parent, string name, Vector2 anchoredPosition, Vector2 size)
        {
            GameObject go = Spawn(name, parent);
            RectTransform rect = go.AddComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.zero;
            rect.pivot = Vector2.zero;
            rect.anchoredPosition = anchoredPosition;
            rect.sizeDelta = size;
            go.AddComponent<Image>().raycastTarget = true;
            return go.AddComponent<Button>();
        }

        private static void DestroyIfAlive(GameObject go)
        {
            if (go != null)
            {
                Object.DestroyImmediate(go);
            }
        }

        private static BridgeRequestContext Body(string json)
        {
            return BridgeRequestContext.ForTests(rawBody: json);
        }

        [Test]
        public void GestureRequests_InvalidTimingArguments_ReturnInvalidArgument()
        {
            object invalidDuration = InteractionGestureRunner.StartLongPress(
                Body("{\"path\":\"Canvas/Button\",\"durationSeconds\":0}"));
            object overflowingDuration = InteractionGestureRunner.StartLongPress(
                Body("{\"path\":\"Canvas/Button\",\"durationSeconds\":1e300}"));
            object invalidSteps = InteractionGestureRunner.StartDrag(
                Body("{\"path\":\"Canvas/Button\",\"deltaX\":1,\"deltaY\":1,\"steps\":0}"));
            object fractionalSteps = InteractionGestureRunner.StartDrag(
                Body("{\"path\":\"Canvas/Button\",\"deltaX\":1,\"deltaY\":1,\"steps\":1.9}"));
            object overflowingDelta = InteractionGestureRunner.StartDrag(
                Body("{\"path\":\"Canvas/Button\",\"deltaX\":1e300,\"deltaY\":1}"));

            Assert.IsInstanceOf<BridgeResponse>(invalidDuration);
            Assert.AreEqual("invalid_argument", ((BridgeResponse)invalidDuration).code);
            Assert.IsInstanceOf<BridgeResponse>(overflowingDuration);
            Assert.AreEqual("invalid_argument", ((BridgeResponse)overflowingDuration).code);
            Assert.IsInstanceOf<BridgeResponse>(invalidSteps);
            Assert.AreEqual("invalid_argument", ((BridgeResponse)invalidSteps).code);
            Assert.IsInstanceOf<BridgeResponse>(fractionalSteps);
            Assert.AreEqual("invalid_argument", ((BridgeResponse)fractionalSteps).code);
            Assert.IsInstanceOf<BridgeResponse>(overflowingDelta);
            Assert.AreEqual("invalid_argument", ((BridgeResponse)overflowingDelta).code);
        }

        [UnityTest]
        public IEnumerator Gestures_CoverCoreScenarios()
        {
            yield return new EnterPlayMode();
            InteractionGestureRunner.ResetForTests();
            JobManager.CompleteAllRunningForTests("gesture-tests");

            IBridgeServiceResolver services = BridgeRuntime.Active?.Services;
            if (services == null || !services.TryGet(out IInteractionGestureBackend _))
            {
                yield return new ExitPlayMode();
                Assert.Ignore("需要已启动且注册了 IInteractionGestureBackend 的 BridgeRuntime（完整 UGUI fixture）");
            }

            EventSystem eventSystem = CreateEventSystem();
            Canvas canvas = CreateOverlayCanvas();

            // --- long-press 事件顺序（不含 pointerClick）---
            {
                Button button = CreateButton(canvas.transform, "Gesture_LongPress", new Vector2(20, 20), new Vector2(120, 60));
                GestureEventProbe probe = button.gameObject.AddComponent<GestureEventProbe>();
                yield return null;

                string path = Mk.UnityAgentBridge.Editor.Hierarchy.NodePath.BuildPath(button.transform);
                object start = InteractionGestureRunner.StartLongPress(
                    Body($"{{\"path\":\"{path}\",\"durationSeconds\":0.15,\"force\":true}}"),
                    services);
                Assert.IsInstanceOf<JsonValue>(start);
                string jobId = ((JsonValue)start)["jobId"].AsString;
                Assert.IsFalse(string.IsNullOrEmpty(jobId));

                float deadline = Time.realtimeSinceStartup + 3f;
                JobRecord job;
                do
                {
                    yield return null;
                    job = JobManager.GetJob(jobId);
                }
                while (job != null && job.Status == JobStatus.Running && Time.realtimeSinceStartup < deadline);

                Assert.IsNotNull(job);
                Assert.AreEqual(JobStatus.Succeeded, job.Status);
                Assert.IsTrue(probe.Events.Contains("pointerEnter"));
                Assert.IsTrue(probe.Events.Contains("pointerDown"));
                Assert.IsTrue(probe.Events.Contains("pointerUp"));
                Assert.IsTrue(probe.Events.Contains("pointerExit"));
                Assert.IsFalse(probe.Events.Contains("pointerClick"));

                DestroyIfAlive(button.gameObject);
            }

            // --- drag 含 beginDrag / drag / endDrag ---
            {
                Button button = CreateButton(canvas.transform, "Gesture_Drag", new Vector2(20, 100), new Vector2(120, 60));
                GestureEventProbe probe = button.gameObject.AddComponent<GestureEventProbe>();
                yield return null;

                string path = Mk.UnityAgentBridge.Editor.Hierarchy.NodePath.BuildPath(button.transform);
                object start = InteractionGestureRunner.StartDrag(
                    Body($"{{\"path\":\"{path}\",\"deltaX\":40,\"deltaY\":10,\"durationSeconds\":0.12,\"steps\":4,\"force\":true}}"),
                    services);
                Assert.IsInstanceOf<JsonValue>(start);
                string jobId = ((JsonValue)start)["jobId"].AsString;

                float deadline = Time.realtimeSinceStartup + 3f;
                JobRecord job;
                do
                {
                    yield return null;
                    job = JobManager.GetJob(jobId);
                }
                while (job != null && job.Status == JobStatus.Running && Time.realtimeSinceStartup < deadline);

                Assert.AreEqual(JobStatus.Succeeded, job.Status);
                Assert.IsTrue(probe.Events.Contains("beginDrag"));
                Assert.IsTrue(probe.Events.Contains("drag"));
                Assert.IsTrue(probe.Events.Contains("endDrag"));
                Assert.Greater(probe.DragCount, 0);
                Dictionary<string, object> result = (Dictionary<string, object>)job.Result;
                Dictionary<string, object> startPoint = (Dictionary<string, object>)result["start"];
                Dictionary<string, object> endPoint = (Dictionary<string, object>)result["end"];
                Assert.AreEqual(40f, (float)endPoint["x"] - (float)startPoint["x"], 0.01f);
                Assert.AreEqual(10f, (float)endPoint["y"] - (float)startPoint["y"], 0.01f);

                DestroyIfAlive(button.gameObject);
            }

            // --- Domain Reload 取消 drag：释放 pointer，但不得触发 drop ---
            {
                Button button = CreateButton(
                    canvas.transform, "Gesture_ReloadCancel", new Vector2(20, 180), new Vector2(120, 60));
                GestureEventProbe probe = button.gameObject.AddComponent<GestureEventProbe>();
                yield return null;

                string path = Mk.UnityAgentBridge.Editor.Hierarchy.NodePath.BuildPath(button.transform);
                object start = InteractionGestureRunner.StartDrag(
                    Body($"{{\"path\":\"{path}\",\"deltaX\":40,\"deltaY\":10,\"durationSeconds\":2,\"steps\":20,\"force\":true}}"),
                    services);
                string jobId = ((JsonValue)start)["jobId"].AsString;
                yield return null;
                if (!probe.Events.Contains("beginDrag"))
                {
                    yield return null;
                }

                Assert.IsTrue(probe.Events.Contains("beginDrag"));
                InteractionGestureRunner.HandleBeforeAssemblyReload();

                JobRecord job = JobManager.GetJob(jobId);
                Assert.AreEqual(JobStatus.Failed, job.Status);
                Assert.AreEqual("interrupted_by_reload", job.ErrorCode);
                Assert.IsTrue(probe.Events.Contains("endDrag"));
                Assert.IsTrue(probe.Events.Contains("pointerUp"));
                Assert.IsTrue(probe.Events.Contains("pointerExit"));
                Assert.AreEqual(0, probe.DropCount);

                DestroyIfAlive(button.gameObject);
            }

            // --- single-flight：第二个手势返回 interaction_busy ---
            {
                Button button = CreateButton(canvas.transform, "Gesture_Busy", new Vector2(20, 260), new Vector2(120, 60));
                yield return null;
                string path = Mk.UnityAgentBridge.Editor.Hierarchy.NodePath.BuildPath(button.transform);

                object first = InteractionGestureRunner.StartLongPress(
                    Body($"{{\"path\":\"{path}\",\"durationSeconds\":0.4,\"force\":true}}"),
                    services);
                Assert.IsInstanceOf<JsonValue>(first);
                object second = InteractionGestureRunner.StartDrag(
                    Body($"{{\"path\":\"{path}\",\"deltaX\":5,\"deltaY\":5,\"force\":true}}"),
                    services);
                Assert.IsInstanceOf<BridgeResponse>(second);
                Assert.AreEqual("interaction_busy", ((BridgeResponse)second).code);

                string jobId = ((JsonValue)first)["jobId"].AsString;
                float deadline = Time.realtimeSinceStartup + 3f;
                JobRecord job;
                do
                {
                    yield return null;
                    job = JobManager.GetJob(jobId);
                }
                while (job != null && job.Status == JobStatus.Running && Time.realtimeSinceStartup < deadline);

                InteractionGestureRunner.ResetForTests();
                DestroyIfAlive(button.gameObject);
            }

            // --- click 回归仍可用 ---
            {
                Button button = CreateButton(canvas.transform, "Gesture_ClickRegression", new Vector2(20, 340), new Vector2(120, 60));
                yield return null;
                PointerSimulator.ClickResult click = PointerSimulator.SimulateClick(button.gameObject, force: true, services);
                Assert.IsTrue(click.Ok);
                Assert.IsTrue(click.Events.Contains("pointerClick"));
                DestroyIfAlive(button.gameObject);
            }

            // --- 遮挡 ---
            {
                Button under = CreateButton(canvas.transform, "Gesture_Under", new Vector2(20, 420), new Vector2(120, 60));
                Button over = CreateButton(canvas.transform, "Gesture_Over", new Vector2(20, 420), new Vector2(120, 60));
                yield return null;
                string path = Mk.UnityAgentBridge.Editor.Hierarchy.NodePath.BuildPath(under.transform);
                object blocked = InteractionGestureRunner.StartLongPress(
                    Body($"{{\"path\":\"{path}\",\"durationSeconds\":0.1,\"force\":false}}"),
                    services);
                Assert.IsInstanceOf<JsonValue>(blocked);
                JsonValue blockedJson = (JsonValue)blocked;
                Assert.IsFalse(blockedJson["ok"].AsBoolean);
                Assert.AreEqual("occluded", blockedJson["code"].AsString);

                DestroyIfAlive(over.gameObject);
                DestroyIfAlive(under.gameObject);
            }

            DestroyIfAlive(canvas.gameObject);
            DestroyIfAlive(eventSystem.gameObject);
            InteractionGestureRunner.ResetForTests();

            yield return new ExitPlayMode();
        }

        private sealed class GestureEventProbe : MonoBehaviour,
            IPointerEnterHandler, IPointerDownHandler, IPointerUpHandler, IPointerExitHandler,
            IPointerClickHandler, IInitializePotentialDragHandler, IBeginDragHandler, IDragHandler,
            IEndDragHandler, IDropHandler
        {
            public readonly List<string> Events = new List<string>();
            public int DragCount;
            public int DropCount;

            public void OnPointerEnter(PointerEventData eventData) => Events.Add("pointerEnter");
            public void OnPointerDown(PointerEventData eventData) => Events.Add("pointerDown");
            public void OnPointerUp(PointerEventData eventData) => Events.Add("pointerUp");
            public void OnPointerExit(PointerEventData eventData) => Events.Add("pointerExit");
            public void OnPointerClick(PointerEventData eventData) => Events.Add("pointerClick");
            public void OnInitializePotentialDrag(PointerEventData eventData) => Events.Add("initializePotentialDrag");
            public void OnBeginDrag(PointerEventData eventData) => Events.Add("beginDrag");
            public void OnDrag(PointerEventData eventData)
            {
                Events.Add("drag");
                DragCount++;
            }

            public void OnEndDrag(PointerEventData eventData) => Events.Add("endDrag");
            public void OnDrop(PointerEventData eventData)
            {
                Events.Add("drop");
                DropCount++;
            }
        }
    }
}
