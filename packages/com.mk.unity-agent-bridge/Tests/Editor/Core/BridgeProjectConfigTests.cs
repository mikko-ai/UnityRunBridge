using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests
{
    public sealed class BridgeProjectConfigTests
    {
        [Test]
        public void FromJson_ReadsPreferredPort()
        {
            string json = @"{
                ""$schema"": ""schemas/config.schema.json"",
                ""version"": 1,
                ""bridge"": { ""preferredPort"": 17891 },
                ""timeouts"": { ""playSeconds"": 180, ""stopSeconds"": 60, ""startEditorSeconds"": 300 }
            }";

            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson(json);

            Assert.AreEqual(17891, settings.preferredPort);
        }

        [Test]
        public void FromJson_UsesDefaultWhenBridgeIsMissing()
        {
            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson("{}");

            Assert.AreEqual(17890, settings.preferredPort);
        }

        [Test]
        public void FromJson_UsesDefaultWhenPreferredPortIsNotPositive()
        {
            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson(@"{""bridge"":{""preferredPort"":0}}");

            Assert.AreEqual(17890, settings.preferredPort);
        }

        [Test]
        public void FromJson_UsesDefaultWhenPreferredPortExceedsMaxPort()
        {
            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson(@"{""bridge"":{""preferredPort"":70000}}");

            Assert.AreEqual(17890, settings.preferredPort);
        }

        [Test]
        public void FromJson_MissingCaptureSection_UsesDefaults()
        {
            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson("{}");

            Assert.IsTrue(settings.ScreenshotCapture.Enabled);
            Assert.IsTrue(settings.ScreenshotCapture.AllowAgentRequest);
            Assert.IsTrue(settings.ScreenshotCapture.OnAssertFailure);
            Assert.IsTrue(settings.ScreenshotCapture.OnScenarioStep);
            Assert.AreEqual(50, settings.ScreenshotCapture.MaxPerSession);
            Assert.AreEqual(1280, settings.ScreenshotCapture.MaxLongEdge);
            Assert.AreEqual("allow", settings.ScreenshotCapture.AgentImageAccess);
        }

        [Test]
        public void FromJson_PartialCaptureSection_KeepsUnspecifiedDefaults()
        {
            string json = @"{""capture"":{""screenshot"":{""enabled"":false,""maxPerSession"":5}}}";

            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson(json);

            Assert.IsFalse(settings.ScreenshotCapture.Enabled);
            Assert.AreEqual(5, settings.ScreenshotCapture.MaxPerSession);
            Assert.IsTrue(settings.ScreenshotCapture.AllowAgentRequest);
            Assert.AreEqual(1280, settings.ScreenshotCapture.MaxLongEdge);
        }

        [Test]
        public void FromJson_CaptureAgentImageAccessDeny_IsParsed()
        {
            string json = @"{""capture"":{""screenshot"":{""agentImageAccess"":""deny""}}}";

            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson(json);

            Assert.AreEqual("deny", settings.ScreenshotCapture.AgentImageAccess);
        }

        [Test]
        public void FromJson_MissingGameplaySection_DefaultsToDisabledAndEmptyWhitelist()
        {
            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson("{}");

            Assert.IsFalse(settings.Gameplay.Enabled);
            Assert.IsNotNull(settings.Gameplay.Whitelist);
            Assert.AreEqual(0, settings.Gameplay.Whitelist.Length);
        }

        [Test]
        public void FromJson_GameplaySection_ReadsEnabledAndWhitelist()
        {
            string json = @"{""gameplay"":{""enabled"":true,""whitelist"":[""MyGame.CheatManager.AddGold""]}}";

            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson(json);

            Assert.IsTrue(settings.Gameplay.Enabled);
            CollectionAssert.AreEqual(new[] { "MyGame.CheatManager.AddGold" }, settings.Gameplay.Whitelist);
        }

        [Test]
        public void FromJson_GameplaySectionWithoutWhitelist_KeepsEmptyArrayDefault()
        {
            string json = @"{""gameplay"":{""enabled"":true}}";

            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson(json);

            Assert.IsTrue(settings.Gameplay.Enabled);
            Assert.AreEqual(0, settings.Gameplay.Whitelist.Length);
        }
    }
}
