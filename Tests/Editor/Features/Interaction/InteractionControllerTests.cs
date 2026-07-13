using Mk.UnityAgentBridge.Editor.Interaction;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Interaction
{
    public sealed class InteractionControllerTests
    {
        private static bool HasInteractionCapability()
        {
            foreach (string capability in CapabilityRegistry.All())
            {
                if (capability == "interaction")
                {
                    return true;
                }
            }

            return false;
        }

        [Test]
        public void Routes_AreRegistered()
        {
            if (!HasInteractionCapability())
            {
                Assert.Ignore("interaction 路由仅在 UGUI Adapter 可用时注册");
            }

            Assert.IsNotNull(RouteTable.Resolve("POST", "interaction/click", out _));
            Assert.IsNotNull(RouteTable.Resolve("POST", "interaction/input", out _));
            Assert.IsNotNull(RouteTable.Resolve("POST", "interaction/set-value", out _));
        }

        [Test]
        public void CapabilitiesResponse_DeclaresInteractionCapability()
        {
            if (!HasInteractionCapability())
            {
                Assert.Ignore("interaction capability 仅在 UGUI Adapter 可用时声明");
            }

            JsonValue response = CapabilitiesController.BuildResponse();
            bool hasInteraction = false;
            foreach (JsonValue capability in response["capabilities"].Items)
            {
                if (capability.AsString == "interaction")
                {
                    hasInteraction = true;
                }
            }

            Assert.IsTrue(hasInteraction);
        }

        [Test]
        public void ValidatePlayModeState_WhenPlaying_Accepts()
        {
            bool ok = InteractionController.ValidatePlayModeState("playing", out BridgeResponse rejection);

            Assert.IsTrue(ok);
            Assert.IsNull(rejection);
        }

        [Test]
        public void ValidatePlayModeState_WhenPausedOrIdle_RejectsWithNotInPlayMode()
        {
            Assert.IsFalse(InteractionController.ValidatePlayModeState("paused", out BridgeResponse pausedRejection));
            Assert.AreEqual("not_in_play_mode", pausedRejection.code);

            Assert.IsFalse(InteractionController.ValidatePlayModeState("idle", out BridgeResponse idleRejection));
            Assert.AreEqual("not_in_play_mode", idleRejection.code);
        }

        [Test]
        public void Click_NotInPlayMode_ReturnsNotInPlayMode()
        {
            // EditMode 测试环境下 EditorApplication.isPlaying 恒为 false，天然覆盖该分支。
            object result = InteractionController.Click(BridgeRequestContext.ForTests(rawBody: "{\"path\":\"Foo\"}"));

            Assert.IsInstanceOf<BridgeResponse>(result);
            Assert.AreEqual("not_in_play_mode", ((BridgeResponse)result).code);
        }

        [Test]
        public void Click_MissingPath_ReturnsInvalidArgument()
        {
            object result = InteractionController.Click(BridgeRequestContext.ForTests(rawBody: "{}"));

            Assert.IsInstanceOf<BridgeResponse>(result);
            Assert.AreEqual("invalid_argument", ((BridgeResponse)result).code);
        }

        [Test]
        public void Input_NotInPlayMode_ReturnsNotInPlayMode()
        {
            object result = InteractionController.Input(BridgeRequestContext.ForTests(rawBody: "{\"path\":\"Foo\",\"text\":\"hi\"}"));

            Assert.IsInstanceOf<BridgeResponse>(result);
            Assert.AreEqual("not_in_play_mode", ((BridgeResponse)result).code);
        }

        [Test]
        public void SetValue_NotInPlayMode_ReturnsNotInPlayMode()
        {
            object result = InteractionController.SetValue(BridgeRequestContext.ForTests(rawBody: "{\"path\":\"Foo\",\"value\":1}"));

            Assert.IsInstanceOf<BridgeResponse>(result);
            Assert.AreEqual("not_in_play_mode", ((BridgeResponse)result).code);
        }
    }
}
