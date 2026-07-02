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
    }
}
