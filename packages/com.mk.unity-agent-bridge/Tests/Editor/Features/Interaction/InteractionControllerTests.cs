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

        [Test]
        public void Click_MissingPath_AuditsNormalizedRequest()
        {
            AssertAuditedFailure("click", "{}", "invalid_argument", request =>
            {
                Assert.IsFalse(request.ContainsKey("path"));
                Assert.IsFalse(request["force"].AsBoolean);
            });
        }

        [Test]
        public void Input_MissingPath_AuditsNormalizedRequest()
        {
            AssertAuditedFailure("input", "{}", "invalid_argument", request =>
            {
                Assert.IsFalse(request.ContainsKey("path"));
                Assert.IsFalse(request["submit"].AsBoolean);
                Assert.IsFalse(request.ContainsKey("text"));
                Assert.IsFalse(request.ContainsKey("textLength"));
            });
        }

        [Test]
        public void SetValue_MissingPath_AuditsNormalizedRequest()
        {
            AssertAuditedFailure("set-value", "{}", "invalid_argument", request =>
            {
                Assert.IsFalse(request.ContainsKey("path"));
                Assert.AreEqual("invalid", request["valueKind"].AsString);
                Assert.IsFalse(request.ContainsKey("value"));
            });
        }

        [Test]
        public void Click_Idle_AuditsNormalizedRequest()
        {
            AssertAuditedFailure(
                "click", "{\"path\":\"Foo\",\"force\":true}", "not_in_play_mode",
                request => AssertClickRequest(request, "Foo"));
        }

        [Test]
        public void Input_Idle_AuditsNormalizedRequest()
        {
            AssertAuditedFailure(
                "input",
                "{\"path\":\"Foo\",\"text\":\"do-not-log-this-secret\",\"submit\":true}",
                "not_in_play_mode",
                request => AssertInputRequest(request, "Foo"));
        }

        [Test]
        public void SetValue_Idle_AuditsNormalizedRequest()
        {
            AssertAuditedFailure(
                "set-value", "{\"path\":\"Foo\",\"value\":1}", "not_in_play_mode",
                request => AssertNumberRequest(request, "Foo", 1));
        }

        [Test]
        public void Click_PlayingWithMissingNode_AuditsNormalizedRequest()
        {
            InteractionController.SetPlayModeStateProviderForTests(() => "playing");

            AssertAuditedFailure(
                "click", "{\"path\":\"Missing\",\"force\":true}", "node_not_found",
                request => AssertClickRequest(request, "Missing"));
        }

        [Test]
        public void Input_PlayingWithMissingNode_AuditsNormalizedRequest()
        {
            InteractionController.SetPlayModeStateProviderForTests(() => "playing");

            AssertAuditedFailure(
                "input",
                "{\"path\":\"Missing\",\"text\":\"do-not-log-this-secret\",\"submit\":true}",
                "node_not_found",
                request => AssertInputRequest(request, "Missing"));
        }

        [Test]
        public void SetValue_PlayingWithMissingNode_AuditsNormalizedRequest()
        {
            InteractionController.SetPlayModeStateProviderForTests(() => "playing");

            AssertAuditedFailure(
                "set-value", "{\"path\":\"Missing\",\"value\":1}", "node_not_found",
                request => AssertNumberRequest(request, "Missing", 1));
        }

        private void AssertAuditedFailure(
            string action,
            string rawBody,
            string expectedCode,
            Action<JsonValue> assertRequest)
        {
            int before = auditLines.Count;
            object result = Invoke(action, rawBody);

            Assert.AreEqual(before + 1, auditLines.Count);
            JsonValue audit = JsonParser.Parse(auditLines[before]);
            Assert.AreEqual(action, audit["action"].AsString);
            Assert.IsFalse(audit["ok"].AsBoolean);
            Assert.AreEqual(expectedCode, audit["code"].AsString);
            Assert.AreEqual(expectedCode, ((BridgeResponse)result).code);
            assertRequest(audit["request"]);
            if (action == "input")
            {
                StringAssert.DoesNotContain(SecretInput, auditLines[before]);
            }
        }

        private static void AssertClickRequest(JsonValue request, string expectedPath)
        {
            Assert.AreEqual(expectedPath, request["path"].AsString);
            Assert.IsTrue(request["force"].AsBoolean);
        }

        private static void AssertInputRequest(JsonValue request, string expectedPath)
        {
            Assert.AreEqual(expectedPath, request["path"].AsString);
            Assert.AreEqual(SecretInput.Length, request["textLength"].AsInt);
            Assert.IsTrue(request["submit"].AsBoolean);
            Assert.IsFalse(request.ContainsKey("text"));
        }

        private static void AssertNumberRequest(JsonValue request, string expectedPath, int expectedValue)
        {
            Assert.AreEqual(expectedPath, request["path"].AsString);
            Assert.AreEqual("number", request["valueKind"].AsString);
            Assert.AreEqual(expectedValue, request["value"].AsInt);
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
