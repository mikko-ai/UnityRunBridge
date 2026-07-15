using System.Collections;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Interaction;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Tests.Interaction
{
    // EventSystem/GraphicRaycaster/Graphic 等 UGUI 组件依赖 OnEnable 完成内部注册
    // （EventSystem.current、GraphicRegistry 等），而纯 EditMode 下 AddComponent 不会触发
    // OnEnable，因此这里用 UnityTest + EnterPlayMode 真正进入 Play Mode 来测试。经验证，
    // 在同一个 batchmode 会话里反复 EnterPlayMode/ExitPlayMode（每个测试方法一次）会让
    // EventSystem/GraphicRaycaster 的内部状态在第二次及之后的循环里变得不可靠（出现无法
    // 解释的 NullReferenceException / 射线检测漏判），因此把所有点击场景合并进同一个
    // UnityTest、共用一次 Play Mode 会话，场景之间通过销毁上一场景的 GameObject 来隔离。
    public sealed class PointerSimulatorTests
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
            GameObject go = Spawn("PointerSimulatorTests_EventSystem");
            return go.AddComponent<EventSystem>();
        }

        private static Canvas CreateOverlayCanvas()
        {
            GameObject go = Spawn("PointerSimulatorTests_Canvas");
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

        [UnityTest]
        public IEnumerator SimulateClick_CoversAllScenarios()
        {
            yield return new EnterPlayMode();

            // --- 场景 1：没有 EventSystem ---
            {
                GameObject lonely = Spawn("PointerSimulatorTests_Lonely");
                lonely.AddComponent<RectTransform>();

                yield return null;

                PointerSimulator.ClickResult result = PointerSimulator.SimulateClick(lonely, force: false);

                Assert.IsFalse(result.Ok);
                Assert.AreEqual("no_event_system", result.ErrorCode);

                DestroyIfAlive(lonely);
            }

            // --- 场景 2：目标节点 inactive ---
            {
                EventSystem eventSystem = CreateEventSystem();
                Canvas canvas = CreateOverlayCanvas();
                Button button = CreateButton(canvas.transform, "PointerSimulatorTests_Inactive", Vector2.zero, new Vector2(100, 50));
                button.gameObject.SetActive(false);

                yield return null;

                PointerSimulator.ClickResult result = PointerSimulator.SimulateClick(button.gameObject, force: false);

                Assert.IsFalse(result.Ok);
                Assert.AreEqual("node_inactive", result.ErrorCode);

                DestroyIfAlive(canvas.gameObject);
                DestroyIfAlive(eventSystem.gameObject);
            }

            // --- 场景 3：无遮挡的正常点击，完整事件链 ---
            {
                EventSystem eventSystem = CreateEventSystem();
                Canvas canvas = CreateOverlayCanvas();
                Button button = CreateButton(canvas.transform, "PointerSimulatorTests_Clickable", new Vector2(100, 100), new Vector2(200, 60));

                bool clicked = false;
                button.onClick.AddListener(() => clicked = true);

                yield return null;

                PointerSimulator.ClickResult result = PointerSimulator.SimulateClick(button.gameObject, force: false);

                Assert.IsTrue(result.Ok, result.ErrorMessage);
                Assert.IsTrue(clicked);
                CollectionAssert.Contains(result.Events, "pointerDown");
                CollectionAssert.Contains(result.Events, "pointerUp");
                CollectionAssert.Contains(result.Events, "pointerClick");
                Assert.AreEqual(button.gameObject, result.Clicked);
                Assert.AreEqual(button.gameObject, result.RaycastHit);
                Assert.IsFalse(result.Forced);

                DestroyIfAlive(canvas.gameObject);
                DestroyIfAlive(eventSystem.gameObject);
            }

            // --- 场景 4：Controller 点击走真实 EventSystem、NodePath 和审计出口 ---
            {
                EventSystem eventSystem = CreateEventSystem();
                Canvas canvas = CreateOverlayCanvas();
                Button button = CreateButton(
                    canvas.transform,
                    "PointerSimulatorTests_ControllerClickable",
                    new Vector2(100, 100),
                    new Vector2(200, 60));
                int clickCount = 0;
                button.onClick.AddListener(() => clickCount++);
                List<string> lines = new List<string>();

                try
                {
                    InteractionAuditLog.SetHooksForTests(
                        () => "/virtual/artifacts",
                        (_, text) => lines.Add(text));

                    yield return null;

                    string path = NodePath.BuildPath(button.transform);
                    object raw = InteractionController.Click(
                        BridgeRequestContext.ForTests(
                            rawBody: $"{{\"path\":\"{path}\",\"force\":false}}"));
                    JsonValue response = (JsonValue)raw;

                    Assert.IsTrue(response["ok"].AsBoolean);
                    Assert.AreEqual(1, clickCount);
                    Assert.IsFalse(response.ContainsKey("code"));
                    Assert.AreEqual(path, response["clicked"].AsString);
                    Assert.AreEqual(1, lines.Count);
                    JsonValue audit = JsonParser.Parse(lines[0]);
                    Assert.IsTrue(audit["ok"].AsBoolean);
                    Assert.AreEqual("ok", audit["code"].AsString);
                    Assert.AreEqual(path, audit["request"]["path"].AsString);
                    CollectionAssert.Contains(
                        audit["events"].Items.ConvertAll(item => item.AsString),
                        "pointerClick");
                }
                finally
                {
                    InteractionAuditLog.ResetForTests();
                    DestroyIfAlive(canvas.gameObject);
                    DestroyIfAlive(eventSystem.gameObject);
                }
            }

            // --- 场景 5：被全屏遮挡层挡住 ---
            {
                EventSystem eventSystem = CreateEventSystem();
                Canvas canvas = CreateOverlayCanvas();
                Button button = CreateButton(canvas.transform, "PointerSimulatorTests_Blocked", new Vector2(100, 100), new Vector2(200, 60));

                GameObject blockerGo = Spawn("PointerSimulatorTests_Blocker", canvas.transform);
                RectTransform blockerRect = blockerGo.AddComponent<RectTransform>();
                blockerRect.anchorMin = Vector2.zero;
                blockerRect.anchorMax = Vector2.one;
                blockerRect.offsetMin = Vector2.zero;
                blockerRect.offsetMax = Vector2.zero;
                blockerGo.AddComponent<Image>().raycastTarget = true;
                // 覆盖层需要在按钮之后添加才会在渲染/命中顺序上位于其上方（Transform 兄弟序即绘制序）。

                yield return null;

                PointerSimulator.ClickResult result = PointerSimulator.SimulateClick(button.gameObject, force: false);

                Assert.IsFalse(result.Ok);
                Assert.AreEqual("occluded", result.ErrorCode, result.ErrorMessage);
                Assert.AreEqual(blockerGo, result.RaycastHit);

                DestroyIfAlive(canvas.gameObject);
                DestroyIfAlive(eventSystem.gameObject);
            }

            // --- 场景 6：force=true 绕过遮挡检测 ---
            {
                EventSystem eventSystem = CreateEventSystem();
                Canvas canvas = CreateOverlayCanvas();
                Button button = CreateButton(canvas.transform, "PointerSimulatorTests_ForceClickable", new Vector2(100, 100), new Vector2(200, 60));

                GameObject blockerGo = Spawn("PointerSimulatorTests_ForceBlocker", canvas.transform);
                RectTransform blockerRect = blockerGo.AddComponent<RectTransform>();
                blockerRect.anchorMin = Vector2.zero;
                blockerRect.anchorMax = Vector2.one;
                blockerRect.offsetMin = Vector2.zero;
                blockerRect.offsetMax = Vector2.zero;
                blockerGo.AddComponent<Image>().raycastTarget = true;

                bool clicked = false;
                button.onClick.AddListener(() => clicked = true);

                yield return null;

                PointerSimulator.ClickResult result = PointerSimulator.SimulateClick(button.gameObject, force: true);

                Assert.IsTrue(result.Ok, result.ErrorMessage);
                Assert.IsTrue(clicked);
                Assert.IsTrue(result.Forced);

                DestroyIfAlive(canvas.gameObject);
                DestroyIfAlive(eventSystem.gameObject);
            }

            // --- 场景 7：interactable=false ---
            {
                EventSystem eventSystem = CreateEventSystem();
                Canvas canvas = CreateOverlayCanvas();
                Button button = CreateButton(canvas.transform, "PointerSimulatorTests_Disabled", new Vector2(100, 100), new Vector2(200, 60));
                button.interactable = false;

                yield return null;

                PointerSimulator.ClickResult result = PointerSimulator.SimulateClick(button.gameObject, force: false);

                Assert.IsFalse(result.Ok);
                Assert.AreEqual("not_interactable", result.ErrorCode, result.ErrorMessage);

                DestroyIfAlive(canvas.gameObject);
                DestroyIfAlive(eventSystem.gameObject);
            }

            yield return new ExitPlayMode();
        }
    }
}
