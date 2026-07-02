using NUnit.Framework;

namespace Elex.UnityAgentBridge.Editor.Tests
{
    public sealed class BridgeProjectConfigTests
    {
        [Test]
        public void FromJson_ReadsBridgeHostAndPort()
        {
            string json = "{\"bridge\":{\"host\":\"127.0.0.1\",\"port\":17891}}";

            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson(json);

            Assert.AreEqual("127.0.0.1", settings.host);
            Assert.AreEqual(17891, settings.port);
        }

        [Test]
        public void FromJson_UsesDefaultsWhenBridgeIsMissing()
        {
            BridgeProjectConfig.Settings settings = BridgeProjectConfig.FromJson("{}");

            Assert.AreEqual("127.0.0.1", settings.host);
            Assert.AreEqual(17890, settings.port);
        }

        [Test]
        public void BuildPrefix_UsesHostAndPort()
        {
            Assert.AreEqual(
                "http://127.0.0.1:17891/",
                BridgeProjectConfig.BuildPrefix("127.0.0.1", 17891)
            );
        }
    }
}
