using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Adapters.UGUI.Tests
{
    /// <summary>UGUI Adapter 最小行为测试：node enrich / text / raycast。不碰全局 Active。</summary>
    public sealed class UguiAdapterBehaviorTests
    {
        private readonly List<GameObject> spawned = new List<GameObject>();
        private BridgeRuntime runtime;

        [SetUp]
        public void SetUp()
        {
            runtime = new BridgeRuntime();
            new UguiBridgeAdapter().RegisterServices(runtime.Services);
        }

        [TearDown]
        public void TearDown()
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

        [Test]
        public void NodeEnricher_WritesInteractableAndAlpha()
        {
            GameObject go = Spawn("UguiEnrich_Button");
            Button button = go.AddComponent<Button>();
            button.interactable = false;
            CanvasGroup group = go.AddComponent<CanvasGroup>();
            group.alpha = 0.4f;

            JsonValue summary = JsonValue.NewObject();
            foreach (INodeEnricher item in runtime.Services.GetAll<INodeEnricher>())
            {
                item.EnrichSummary(go, summary);
            }

            Assert.IsFalse(summary["interactable"].AsBoolean);
            Assert.AreEqual(0.4f, summary["alpha"].AsFloat, 0.0001f);
        }

        [Test]
        public void TextAdapter_TryGetText_FromUiText()
        {
            GameObject go = Spawn("UguiText");
            Text text = go.AddComponent<Text>();
            text.text = "购买";

            bool found = false;
            string value = null;
            foreach (ITextControlAdapter item in runtime.Services.GetAll<ITextControlAdapter>())
            {
                if (item.TryGetText(go, out value))
                {
                    found = true;
                    break;
                }
            }

            Assert.IsTrue(found);
            Assert.AreEqual("购买", value);
        }

        [Test]
        public void InteractionBackend_NoEventSystem_ReturnsNoEventSystem()
        {
            GameObject go = Spawn("UguiClick_NoEs");
            go.AddComponent<RectTransform>();
            go.AddComponent<Button>();

            Assert.IsTrue(runtime.Services.TryGet(out IInteractionBackend backend));
            InteractionOperationResult result = backend.Click(go, force: true);
            Assert.IsFalse(result.Ok);
            Assert.AreEqual("no_event_system", result.ErrorCode);
        }

        [Test]
        public void AnnotationBackend_IsRegistered()
        {
            Assert.IsTrue(runtime.Services.TryGet(out IUiAnnotationBackend backend));
            Assert.IsNotNull(backend);
        }

        [Test]
        public void HitTestBackend_IsRegistered()
        {
            Assert.IsTrue(runtime.Services.TryGet(out IUiHitTestBackend backend));
            Assert.IsNotNull(backend);
            IReadOnlyList<UiHitResult> hits = backend.Raycast(new Vector2(10, 10));
            Assert.IsNotNull(hits);
        }

        [Test]
        public void GestureBackend_IsRegistered()
        {
            Assert.IsTrue(runtime.Services.TryGet(out IInteractionGestureBackend backend));
            Assert.IsNotNull(backend);
        }

        [Test]
        public void AnnotationBackend_IndexToLabel_IsStable()
        {
            Assert.AreEqual("A", UguiAnnotationBackend.IndexToLabel(0));
            Assert.AreEqual("Z", UguiAnnotationBackend.IndexToLabel(25));
            Assert.AreEqual("AA", UguiAnnotationBackend.IndexToLabel(26));
        }

        [Test]
        public void RecordingSemantic_ResolveClickTarget_DoesNotThrow()
        {
            Spawn("UguiRaycast_ES").AddComponent<EventSystem>();
            GameObject canvasGo = Spawn("UguiRaycast_Canvas");
            Canvas canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvasGo.AddComponent<GraphicRaycaster>();

            Assert.IsTrue(runtime.Services.TryGet(out IRecordingSemanticBackend semantic));
            Assert.DoesNotThrow(() => semantic.ResolveClickTarget(new Vector2(150, 130)));
        }
    }
}
