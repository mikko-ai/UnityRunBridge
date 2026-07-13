using System;
using Mk.UnityAgentBridge.Editor.Gameplay;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Gameplay
{
    public sealed class GameplayControllerTests
    {
        [Test]
        public void Routes_AreRegistered()
        {
            Assert.IsNotNull(RouteTable.Resolve("GET", "gameplay/commands", out _));
            Assert.IsNotNull(RouteTable.Resolve("POST", "gameplay/invoke", out _));
        }

        [Test]
        public void CapabilitiesResponse_DeclaresGameplayCapability()
        {
            JsonValue response = CapabilitiesController.BuildResponse();
            bool hasGameplay = false;
            foreach (JsonValue capability in response["capabilities"].Items)
            {
                if (capability.AsString == "gameplay")
                {
                    hasGameplay = true;
                }
            }

            Assert.IsTrue(hasGameplay);
        }

        [Test]
        public void ValidateGateState_WhenDisabled_ReturnsGameplayDisabled()
        {
            BridgeProjectConfig.GameplaySettings settings =
                new BridgeProjectConfig.GameplaySettings { Enabled = false, Whitelist = Array.Empty<string>() };

            bool ok = GameplayController.ValidateGateState(settings, "playing", out BridgeResponse rejection);

            Assert.IsFalse(ok);
            Assert.AreEqual("gameplay_disabled", rejection.code);
        }

        [Test]
        public void ValidateGateState_WhenEnabledButNotPlaying_ReturnsNotInPlayMode()
        {
            BridgeProjectConfig.GameplaySettings settings =
                new BridgeProjectConfig.GameplaySettings { Enabled = true, Whitelist = Array.Empty<string>() };

            bool ok = GameplayController.ValidateGateState(settings, "idle", out BridgeResponse rejection);

            Assert.IsFalse(ok);
            Assert.AreEqual("not_in_play_mode", rejection.code);
        }

        [Test]
        public void ValidateGateState_WhenEnabledAndPlaying_Accepts()
        {
            BridgeProjectConfig.GameplaySettings settings =
                new BridgeProjectConfig.GameplaySettings { Enabled = true, Whitelist = Array.Empty<string>() };

            bool ok = GameplayController.ValidateGateState(settings, "playing", out BridgeResponse rejection);

            Assert.IsTrue(ok);
            Assert.IsNull(rejection);
        }

        [Test]
        public void Invoke_MissingCommand_ReturnsInvalidArgument()
        {
            object result = GameplayController.Invoke(BridgeRequestContext.ForTests(rawBody: "{}"));

            Assert.IsInstanceOf<BridgeResponse>(result);
            Assert.AreEqual("invalid_argument", ((BridgeResponse)result).code);
        }

        [Test]
        public void Invoke_GameplayDisabledByDefaultTestProjectConfig_ReturnsGameplayDisabled()
        {
            // .tmp/unity-test-project 的 .unity-agent/config.json 没有 "gameplay" 段，
            // BridgeProjectConfig.Load() 因此按安全默认返回 enabled=false。
            object result = GameplayController.Invoke(
                BridgeRequestContext.ForTests(rawBody: "{\"command\":\"Foo.Bar\"}"));

            Assert.IsInstanceOf<BridgeResponse>(result);
            Assert.AreEqual("gameplay_disabled", ((BridgeResponse)result).code);
        }

        [Test]
        public void ListCommands_GameplayDisabledByDefaultTestProjectConfig_ReturnsGameplayDisabled()
        {
            object result = GameplayController.ListCommands(BridgeRequestContext.ForTests());

            Assert.IsInstanceOf<BridgeResponse>(result);
            Assert.AreEqual("gameplay_disabled", ((BridgeResponse)result).code);
        }
    }
}
