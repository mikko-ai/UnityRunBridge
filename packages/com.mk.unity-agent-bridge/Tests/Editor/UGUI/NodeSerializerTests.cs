using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Tests.Hierarchy
{
    public sealed class NodeSerializerTests
    {
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

        private GameObject Spawn(string name, Transform parent = null)
        {
            GameObject go = new GameObject(name);
            if (parent != null)
            {
                go.transform.SetParent(parent, worldPositionStays: false);
            }

            spawned.Add(go);
            return go;
        }

        [Test]
        public void BuildSummary_BaseFieldsAlwaysPresent()
        {
            GameObject go = Spawn("NodeSerializerTests_Base");

            JsonValue summary = NodeSerializer.BuildSummary(go.transform);

            Assert.AreEqual("NodeSerializerTests_Base", summary["name"].AsString);
            Assert.AreEqual(go.GetInstanceID(), summary["instanceId"].AsInt);
            Assert.IsTrue(summary["activeSelf"].AsBoolean);
            Assert.IsTrue(summary["activeInHierarchy"].AsBoolean);
            Assert.AreEqual("Untagged", summary["tag"].AsString);
            Assert.AreEqual(0, summary["layer"].AsInt);
            Assert.AreEqual(0, summary["childCount"].AsInt);
            Assert.IsTrue(summary["componentTypes"].IsArray);
        }

        [Test]
        public void BuildSummary_OptionalFieldsOmittedWithoutComponents()
        {
            GameObject go = Spawn("NodeSerializerTests_NoOptional");

            JsonValue summary = NodeSerializer.BuildSummary(go.transform);

            Assert.IsFalse(summary.ContainsKey("text"));
            Assert.IsFalse(summary.ContainsKey("interactable"));
            Assert.IsFalse(summary.ContainsKey("screenRect"));
            Assert.IsFalse(summary.ContainsKey("alpha"));
            Assert.IsFalse(summary.ContainsKey("renderMode"));
            Assert.IsFalse(summary.ContainsKey("sortingOrder"));
        }

        [Test]
        public void BuildSummary_TextComponent_PopulatesText()
        {
            GameObject go = Spawn("NodeSerializerTests_Text");
            Text text = go.AddComponent<Text>();
            text.text = "购买";

            JsonValue summary = NodeSerializer.BuildSummary(go.transform);

            Assert.AreEqual("购买", summary["text"].AsString);
        }

        [Test]
        public void BuildSummary_ButtonComponent_PopulatesInteractable()
        {
            GameObject go = Spawn("NodeSerializerTests_Button");
            Button button = go.AddComponent<Button>();
            button.interactable = false;

            JsonValue summary = NodeSerializer.BuildSummary(go.transform);

            Assert.IsFalse(summary["interactable"].AsBoolean);
        }

        [Test]
        public void BuildSummary_CanvasGroup_PopulatesAlpha()
        {
            GameObject go = Spawn("NodeSerializerTests_CanvasGroup");
            CanvasGroup group = go.AddComponent<CanvasGroup>();
            group.alpha = 0.5f;

            JsonValue summary = NodeSerializer.BuildSummary(go.transform);

            Assert.AreEqual(0.5f, summary["alpha"].AsFloat, 0.0001f);
        }

        [Test]
        public void BuildSummary_Canvas_PopulatesRenderModeAndSortingOrder()
        {
            GameObject go = Spawn("NodeSerializerTests_Canvas");
            Canvas canvas = go.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 7;

            JsonValue summary = NodeSerializer.BuildSummary(go.transform);

            Assert.AreEqual("ScreenSpaceOverlay", summary["renderMode"].AsString);
            Assert.AreEqual(7, summary["sortingOrder"].AsInt);
        }

        [Test]
        public void BuildSummary_RectTransformWithPointAnchor_ScreenRectMatchesSizeDelta()
        {
            GameObject canvasGo = Spawn("NodeSerializerTests_ScreenRectCanvas");
            Canvas canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;

            GameObject childGo = Spawn("NodeSerializerTests_ScreenRectChild", canvasGo.transform);
            RectTransform rectTransform = childGo.AddComponent<RectTransform>();
            rectTransform.anchorMin = Vector2.zero;
            rectTransform.anchorMax = Vector2.zero;
            rectTransform.pivot = Vector2.zero;
            rectTransform.sizeDelta = new Vector2(200f, 60f);
            rectTransform.anchoredPosition = Vector2.zero;

            JsonValue summary = NodeSerializer.BuildSummary(rectTransform);

            Assert.IsTrue(summary.ContainsKey("screenRect"));
            Assert.AreEqual(200f, summary["screenRect"]["w"].AsFloat, 0.5f);
            Assert.AreEqual(60f, summary["screenRect"]["h"].AsFloat, 0.5f);
        }

        [Test]
        public void ComputeEffectiveInteractable_ParentCanvasGroupBlocksRaycasts_ReturnsFalse()
        {
            GameObject parentGo = Spawn("NodeSerializerTests_EffectiveParent");
            CanvasGroup canvasGroup = parentGo.AddComponent<CanvasGroup>();
            canvasGroup.interactable = true;
            canvasGroup.blocksRaycasts = false;

            GameObject childGo = Spawn("NodeSerializerTests_EffectiveChild", parentGo.transform);
            Button button = childGo.AddComponent<Button>();
            button.interactable = true;

            Assert.IsFalse(NodeSerializer.ComputeEffectiveInteractable(childGo));
        }

        [Test]
        public void ComputeEffectiveInteractable_NoBlockingAncestors_ReturnsTrue()
        {
            GameObject childGo = Spawn("NodeSerializerTests_EffectiveNoBlock");
            Button button = childGo.AddComponent<Button>();
            button.interactable = true;

            Assert.IsTrue(NodeSerializer.ComputeEffectiveInteractable(childGo));
        }

        [Test]
        public void ComputeEffectiveInteractable_SelfNotInteractable_ReturnsFalse()
        {
            GameObject childGo = Spawn("NodeSerializerTests_EffectiveSelfFalse");
            Button button = childGo.AddComponent<Button>();
            button.interactable = false;

            Assert.IsFalse(NodeSerializer.ComputeEffectiveInteractable(childGo));
        }

        [Test]
        public void HasMissingScript_NormalObject_ReturnsFalse()
        {
            GameObject go = Spawn("NodeSerializerTests_NoMissingScript");
            go.AddComponent<BoxCollider>();

            Assert.IsFalse(NodeSerializer.HasMissingScript(go));
        }
    }
}
