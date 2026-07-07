using System.Collections;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Recording;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Tests.Recording
{
    // RecordingListener 本身是纯静态类（不是 MonoBehaviour），但它依赖的 EventSystem/
    // GraphicRaycaster/Graphic 等 UGUI 组件的 OnEnable 注册在纯 EditMode 下不可靠
    // （同 PointerSimulatorTests 的结论），因此点击相关场景仍用 UnityTest + EnterPlayMode。
    // RecordingListener 是进程内全局单例状态，每个场景前后都要 ResetForTests() 避免互相污染。
    public sealed class RecordingListenerTests
    {
        [SetUp]
        public void ResetListener()
        {
            RecordingListener.ResetForTests();
        }

        [TearDown]
        public void TearDown()
        {
            RecordingListener.ResetForTests();
        }

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
            return Spawn("RecordingListenerTests_EventSystem").AddComponent<EventSystem>();
        }

        private static Canvas CreateOverlayCanvas()
        {
            GameObject go = Spawn("RecordingListenerTests_Canvas");
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
        public IEnumerator ProcessPointerDownUp_CoversAllScenarios()
        {
            yield return new EnterPlayMode();

            // --- 场景 1：down 和 up 命中同一个可点击目标 -> 记录 click ---
            {
                EventSystem eventSystem = CreateEventSystem();
                Canvas canvas = CreateOverlayCanvas();
                CreateButton(canvas.transform, "RecordingListenerTests_Button", new Vector2(100, 100), new Vector2(200, 60));
                List<RecordedAction> recorded = new List<RecordedAction>();
                RecordingListener.StartListening(recorded.Add);

                yield return null;

                Vector2 insideButton = new Vector2(150, 130);
                RecordingListener.ProcessPointerDown(insideButton);
                RecordingListener.ProcessPointerUp(insideButton);

                Assert.AreEqual(1, recorded.Count);
                Assert.AreEqual("click", recorded[0].Type);
                Assert.AreEqual("RecordingListenerTests_Canvas/RecordingListenerTests_Button", recorded[0].Path);
                Assert.AreEqual(insideButton.x, recorded[0].ScreenX);
                Assert.AreEqual(insideButton.y, recorded[0].ScreenY);

                RecordingListener.ResetForTests();
                DestroyIfAlive(canvas.gameObject);
                DestroyIfAlive(eventSystem.gameObject);
            }

            // --- 场景 2：down 在按钮上，up 在空白处 -> 不记录 ---
            {
                EventSystem eventSystem = CreateEventSystem();
                Canvas canvas = CreateOverlayCanvas();
                CreateButton(canvas.transform, "RecordingListenerTests_DragOff", new Vector2(100, 100), new Vector2(200, 60));
                List<RecordedAction> recorded = new List<RecordedAction>();
                RecordingListener.StartListening(recorded.Add);

                yield return null;

                RecordingListener.ProcessPointerDown(new Vector2(150, 130));
                RecordingListener.ProcessPointerUp(new Vector2(900, 900));

                Assert.AreEqual(0, recorded.Count);

                RecordingListener.ResetForTests();
                DestroyIfAlive(canvas.gameObject);
                DestroyIfAlive(eventSystem.gameObject);
            }

            // --- 场景 3：点击空白区域（没有 click handler）-> 不记录 ---
            {
                EventSystem eventSystem = CreateEventSystem();
                Canvas canvas = CreateOverlayCanvas();
                List<RecordedAction> recorded = new List<RecordedAction>();
                RecordingListener.StartListening(recorded.Add);

                yield return null;

                RecordingListener.ProcessPointerDown(new Vector2(10, 10));
                RecordingListener.ProcessPointerUp(new Vector2(10, 10));

                Assert.AreEqual(0, recorded.Count);

                RecordingListener.ResetForTests();
                DestroyIfAlive(canvas.gameObject);
                DestroyIfAlive(eventSystem.gameObject);
            }

            yield return new ExitPlayMode();
        }

        [UnityTest]
        public IEnumerator ProcessSelectionChanged_CoversAllScenarios()
        {
            yield return new EnterPlayMode();

            // --- 场景 1：InputField 失焦（切到别的对象）-> 记录 input，text 为失焦时的最终内容 ---
            {
                GameObject fieldGo = Spawn("RecordingListenerTests_InputField");
                InputField field = fieldGo.AddComponent<InputField>();
                field.text = "hello";
                GameObject other = Spawn("RecordingListenerTests_Other");

                List<RecordedAction> recorded = new List<RecordedAction>();
                RecordingListener.StartListening(recorded.Add);

                yield return null;

                RecordingListener.ProcessSelectionChanged(fieldGo);
                RecordingListener.ProcessSelectionChanged(other);

                Assert.AreEqual(1, recorded.Count);
                Assert.AreEqual("input", recorded[0].Type);
                Assert.AreEqual("hello", recorded[0].Text);
                Assert.AreEqual("RecordingListenerTests_InputField", recorded[0].Path);

                RecordingListener.ResetForTests();
                DestroyIfAlive(fieldGo);
                DestroyIfAlive(other);
            }

            // --- 场景 2：选中对象不是输入框 -> 不记录 ---
            {
                GameObject plain = Spawn("RecordingListenerTests_Plain");
                GameObject other = Spawn("RecordingListenerTests_Other2");
                List<RecordedAction> recorded = new List<RecordedAction>();
                RecordingListener.StartListening(recorded.Add);

                yield return null;

                RecordingListener.ProcessSelectionChanged(plain);
                RecordingListener.ProcessSelectionChanged(other);

                Assert.AreEqual(0, recorded.Count);

                RecordingListener.ResetForTests();
                DestroyIfAlive(plain);
                DestroyIfAlive(other);
            }

            // --- 场景 3：StopListening 时仍有未失焦的输入框 -> 收尾记录一次 ---
            {
                GameObject fieldGo = Spawn("RecordingListenerTests_InputFieldOnStop");
                InputField field = fieldGo.AddComponent<InputField>();
                field.text = "unsaved";

                List<RecordedAction> recorded = new List<RecordedAction>();
                RecordingListener.StartListening(recorded.Add);

                yield return null;

                RecordingListener.ProcessSelectionChanged(fieldGo);
                RecordingListener.StopListening();

                Assert.AreEqual(1, recorded.Count);
                Assert.AreEqual("input", recorded[0].Type);
                Assert.AreEqual("unsaved", recorded[0].Text);

                DestroyIfAlive(fieldGo);
            }

            yield return new ExitPlayMode();
        }

        [Test]
        public void TryGetInputFieldText_UgUiInputField_ReturnsText()
        {
            GameObject go = new GameObject("RecordingListenerTests_DirectField");
            try
            {
                InputField field = go.AddComponent<InputField>();
                field.text = "direct-value";

                bool ok = RecordingListener.TryGetInputFieldText(go, out string text);

                Assert.IsTrue(ok);
                Assert.AreEqual("direct-value", text);
            }
            finally
            {
                Object.DestroyImmediate(go);
            }
        }

        [Test]
        public void TryGetInputFieldText_PlainGameObject_ReturnsFalse()
        {
            GameObject go = new GameObject("RecordingListenerTests_PlainField");
            try
            {
                bool ok = RecordingListener.TryGetInputFieldText(go, out string text);

                Assert.IsFalse(ok);
                Assert.IsNull(text);
            }
            finally
            {
                Object.DestroyImmediate(go);
            }
        }

        [Test]
        public void StartListening_TwiceInARow_SecondCallIsNoOp()
        {
            List<RecordedAction> firstRecorded = new List<RecordedAction>();
            List<RecordedAction> secondRecorded = new List<RecordedAction>();

            RecordingListener.StartListening(firstRecorded.Add);
            RecordingListener.StartListening(secondRecorded.Add);
            Assert.IsTrue(RecordingListener.IsListening);

            RecordingListener.ProcessPointerUp(Vector2.zero); // 不应抛异常，纯粹验证状态未被二次订阅打乱
            RecordingListener.StopListening();
            Assert.IsFalse(RecordingListener.IsListening);
        }
    }
}
