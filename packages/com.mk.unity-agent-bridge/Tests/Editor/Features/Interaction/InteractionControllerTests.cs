using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Interaction;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Interaction
{
    public sealed class InteractionControllerTests
    {
        private const string SecretInput = "do-not-log-this-secret";
        private List<string> auditLines;

        [SetUp]
        public void SetUp()
        {
            auditLines = new List<string>();
            InteractionAuditLog.SetHooksForTests(
                () => "/virtual/artifacts",
                (_, text) => auditLines.Add(text));
        }

        [TearDown]
        public void TearDown()
        {
            InteractionController.ResetForTests();
            InteractionAuditLog.ResetForTests();
        }

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

        [TestCase("click", "{}")]
        [TestCase("input", "{\"text\":\"do-not-log-this-secret\"}")]
        [TestCase("set-value", "{\"value\":1}")]
        public void MissingPath_AuditsInvalidArgument(string action, string rawBody)
        {
            AssertAuditedFailure(action, rawBody, "invalid_argument");
        }

        [TestCase("click", "{\"path\":\"Foo\"}")]
        [TestCase("input", "{\"path\":\"Foo\",\"text\":\"do-not-log-this-secret\"}")]
        [TestCase("set-value", "{\"path\":\"Foo\",\"value\":1}")]
        public void Idle_AuditsNotInPlayMode(string action, string rawBody)
        {
            AssertAuditedFailure(action, rawBody, "not_in_play_mode");
        }

        [TestCase("click", "{\"path\":\"Missing\"}")]
        [TestCase("input", "{\"path\":\"Missing\",\"text\":\"do-not-log-this-secret\"}")]
        [TestCase("set-value", "{\"path\":\"Missing\",\"value\":1}")]
        public void PlayingWithMissingNode_AuditsNodeNotFound(string action, string rawBody)
        {
            InteractionController.SetPlayModeStateProviderForTests(() => "playing");

            AssertAuditedFailure(action, rawBody, "node_not_found");
        }

        private void AssertAuditedFailure(string action, string rawBody, string expectedCode)
        {
            int before = auditLines.Count;
            object result = Invoke(action, rawBody);

            Assert.AreEqual(before + 1, auditLines.Count);
            JsonValue audit = JsonParser.Parse(auditLines[before]);
            Assert.AreEqual(action, audit["action"].AsString);
            Assert.IsFalse(audit["ok"].AsBoolean);
            Assert.AreEqual(expectedCode, audit["code"].AsString);
            Assert.AreEqual(expectedCode, ((BridgeResponse)result).code);
            if (action == "input")
            {
                StringAssert.DoesNotContain(SecretInput, auditLines[before]);
            }
        }

        private static object Invoke(string action, string rawBody)
        {
            BridgeRequestContext context = BridgeRequestContext.ForTests(rawBody: rawBody);
            switch (action)
            {
                case "click":
                    return InteractionController.Click(context);
                case "input":
                    return InteractionController.Input(context);
                case "set-value":
                    return InteractionController.SetValue(context);
                default:
                    throw new ArgumentOutOfRangeException(nameof(action));
            }
        }
    }
}
