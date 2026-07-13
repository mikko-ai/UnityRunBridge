using System.Collections;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Interaction;
using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Tests.Interaction
{
    public sealed class InputSimulatorTests
    {
        // SetValue_* 系列测试直接读写组件字段，不依赖 EventSystem/OnEnable 注册，用普通
        // EditMode [Test] + 手动清理即可。SetText_* 系列依赖 EventSystem.current（选中/取消选中、
        // Submit 流程），其注册只在真正的 Play Mode 下触发，因此改用 UnityTest + EnterPlayMode。
        // 经验证，在同一个 batchmode 会话里反复 EnterPlayMode/ExitPlayMode（每个测试方法一次）
        // 会让 EventSystem 的内部状态在第二次及之后的循环里变得不可靠，因此把所有 SetText 场景
        // 合并进同一个 UnityTest、共用一次 Play Mode 会话，场景之间通过销毁上一场景的 GameObject
        // 来隔离；额外的 `yield return null` 用于等待同帧内 AddComponent 触发的 OnEnable 注册
        // （EventSystem.current 等）完全生效。
        private readonly List<GameObject> spawned = new List<GameObject>();

        [TearDown]
        public void Cleanup()
        {
            foreach (GameObject go in spawned)
            {
                if (go != null)
                {
                    Object.DestroyImmediate(go);
                }
            }

            spawned.Clear();
        }

        private GameObject Spawn(string name)
        {
            GameObject go = new GameObject(name);
            spawned.Add(go);
            return go;
        }

        private static GameObject SpawnPlay(List<GameObject> tracked, string name)
        {
            GameObject go = new GameObject(name);
            tracked.Add(go);
            return go;
        }

        private static EventSystem CreateEventSystemPlay(List<GameObject> tracked)
        {
            return SpawnPlay(tracked, "InputSimulatorTests_EventSystem").AddComponent<EventSystem>();
        }

        private static InputField CreateInputFieldPlay(List<GameObject> tracked, string name)
        {
            GameObject go = SpawnPlay(tracked, name);
            go.AddComponent<RectTransform>();
            GameObject textGo = new GameObject("Text");
            textGo.transform.SetParent(go.transform, false);
            Text text = textGo.AddComponent<Text>();
            InputField field = go.AddComponent<InputField>();
            field.textComponent = text;
            return field;
        }

        private static void DestroyIfAlive(GameObject go)
        {
            if (go != null)
            {
                Object.DestroyImmediate(go);
            }
        }

        [UnityTest]
        public IEnumerator SetText_CoversAllScenarios()
        {
            yield return new EnterPlayMode();

            // --- 场景 1：没有 EventSystem ---
            {
                List<GameObject> tracked = new List<GameObject>();
                InputField field = CreateInputFieldPlay(tracked, "InputSimulatorTests_NoES");

                yield return null;

                InputSimulator.OperationResult result = InputSimulator.SetText(field.gameObject, "hello", submit: false);

                Assert.IsFalse(result.Ok);
                Assert.AreEqual("no_event_system", result.ErrorCode);

                foreach (GameObject go in tracked) DestroyIfAlive(go);
            }

            // --- 场景 2：目标不是 InputField ---
            {
                List<GameObject> tracked = new List<GameObject>();
                CreateEventSystemPlay(tracked);
                GameObject go = SpawnPlay(tracked, "InputSimulatorTests_Plain");

                yield return null;

                InputSimulator.OperationResult result = InputSimulator.SetText(go, "hello", submit: false);

                Assert.IsFalse(result.Ok);
                Assert.AreEqual("not_input_field", result.ErrorCode);

                foreach (GameObject g in tracked) DestroyIfAlive(g);
            }

            // --- 场景 3：正常输入，触发 onValueChanged ---
            {
                List<GameObject> tracked = new List<GameObject>();
                CreateEventSystemPlay(tracked);
                InputField field = CreateInputFieldPlay(tracked, "InputSimulatorTests_Valid");
                string observed = null;
                field.onValueChanged.AddListener(value => observed = value);

                yield return null;

                InputSimulator.OperationResult result = InputSimulator.SetText(field.gameObject, "player1", submit: false);

                Assert.IsTrue(result.Ok, result.ErrorMessage);
                Assert.AreEqual("player1", field.text);
                Assert.AreEqual("player1", observed);

                foreach (GameObject go in tracked) DestroyIfAlive(go);
            }

            // --- 场景 4：submit=true 触发 onEndEdit 并取消选中 ---
            {
                List<GameObject> tracked = new List<GameObject>();
                EventSystem eventSystem = CreateEventSystemPlay(tracked);
                InputField field = CreateInputFieldPlay(tracked, "InputSimulatorTests_Submit");
                string endEditValue = null;
                field.onEndEdit.AddListener(value => endEditValue = value);

                yield return null;

                InputSimulator.OperationResult result = InputSimulator.SetText(field.gameObject, "done", submit: true);

                Assert.IsTrue(result.Ok, result.ErrorMessage);
                Assert.AreEqual("done", endEditValue);
                Assert.IsNull(eventSystem.currentSelectedGameObject);

                foreach (GameObject go in tracked) DestroyIfAlive(go);
            }

            // --- 场景 5：interactable=false ---
            {
                List<GameObject> tracked = new List<GameObject>();
                CreateEventSystemPlay(tracked);
                InputField field = CreateInputFieldPlay(tracked, "InputSimulatorTests_Disabled");
                field.interactable = false;

                yield return null;

                InputSimulator.OperationResult result = InputSimulator.SetText(field.gameObject, "hello", submit: false);

                Assert.IsFalse(result.Ok);
                Assert.AreEqual("not_interactable", result.ErrorCode);

                foreach (GameObject go in tracked) DestroyIfAlive(go);
            }

            yield return new ExitPlayMode();
        }

        [Test]
        public void SetValue_Slider_SetsValue()
        {
            GameObject go = Spawn("InputSimulatorTests_Slider");
            Slider slider = go.AddComponent<Slider>();
            slider.minValue = 0;
            slider.maxValue = 1;

            InputSimulator.OperationResult result = InputSimulator.SetValue(go, null, JsonValue.FromDouble(0.75));

            Assert.IsTrue(result.Ok, result.ErrorMessage);
            Assert.AreEqual(0.75f, slider.value, 0.001f);
            Assert.AreEqual("Slider", result.ComponentType);
        }

        [Test]
        public void SetValue_Toggle_SetsIsOn()
        {
            GameObject go = Spawn("InputSimulatorTests_Toggle");
            Toggle toggle = go.AddComponent<Toggle>();
            toggle.isOn = false;

            InputSimulator.OperationResult result = InputSimulator.SetValue(go, null, JsonValue.FromBoolean(true));

            Assert.IsTrue(result.Ok, result.ErrorMessage);
            Assert.IsTrue(toggle.isOn);
        }

        [Test]
        public void SetValue_ScrollRect_SetsNormalizedPosition()
        {
            GameObject go = Spawn("InputSimulatorTests_ScrollRect");
            ScrollRect scrollRect = go.AddComponent<ScrollRect>();
            GameObject contentGo = new GameObject("Content");
            contentGo.transform.SetParent(go.transform, false);
            RectTransform contentRect = contentGo.AddComponent<RectTransform>();
            contentRect.sizeDelta = new Vector2(400, 400);
            scrollRect.content = contentRect;

            JsonValue value = JsonValue.NewObject();
            value["x"] = 0.25;
            value["y"] = 0.5;

            InputSimulator.OperationResult result = InputSimulator.SetValue(go, null, value);

            Assert.IsTrue(result.Ok, result.ErrorMessage);
            Assert.AreEqual(0.25f, scrollRect.normalizedPosition.x, 0.001f);
            Assert.AreEqual(0.5f, scrollRect.normalizedPosition.y, 0.001f);
        }

        [Test]
        public void SetValue_NoSupportedComponent_ReturnsUnsupportedSetValue()
        {
            GameObject go = Spawn("InputSimulatorTests_Unsupported");

            InputSimulator.OperationResult result = InputSimulator.SetValue(go, null, JsonValue.FromDouble(1));

            Assert.IsFalse(result.Ok);
            Assert.AreEqual("unsupported_set_value", result.ErrorCode);
        }

        [Test]
        public void SetValue_AmbiguousComponents_ReturnsAmbiguousComponent()
        {
            // Slider 与 ScrollRect 不是同一 Selectable 组，可以共存于一个 GameObject 上，
            // 用来构造「两个受支持的可设值组件」的歧义场景（Slider 与 Scrollbar/Toggle/Dropdown
            // 同属 Selectable，Unity 不允许共存，不能拿来测试这种歧义）。
            GameObject go = Spawn("InputSimulatorTests_Ambiguous");
            go.AddComponent<Slider>();
            go.AddComponent<ScrollRect>();

            InputSimulator.OperationResult result = InputSimulator.SetValue(go, null, JsonValue.FromDouble(0.5));

            Assert.IsFalse(result.Ok);
            Assert.AreEqual("ambiguous_component", result.ErrorCode);
        }

        [Test]
        public void SetValue_ExplicitComponentHint_ResolvesAmbiguity()
        {
            GameObject go = Spawn("InputSimulatorTests_Explicit");
            Slider slider = go.AddComponent<Slider>();
            slider.minValue = 0;
            slider.maxValue = 1;
            go.AddComponent<ScrollRect>();

            InputSimulator.OperationResult result = InputSimulator.SetValue(go, "Slider", JsonValue.FromDouble(0.2));

            Assert.IsTrue(result.Ok, result.ErrorMessage);
            Assert.AreEqual(0.2f, slider.value, 0.001f);
        }

        [Test]
        public void SetValue_WrongValueType_ReturnsInvalidArgument()
        {
            GameObject go = Spawn("InputSimulatorTests_WrongType");
            go.AddComponent<Toggle>();

            InputSimulator.OperationResult result = InputSimulator.SetValue(go, null, JsonValue.FromDouble(1));

            Assert.IsFalse(result.Ok);
            Assert.AreEqual("invalid_argument", result.ErrorCode);
        }
    }
}
