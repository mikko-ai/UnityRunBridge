using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests
{
    public sealed class BridgeServerTests
    {
        [Test]
        public void BuildCandidatePorts_ReturnsConsecutivePortsStartingFromPreferred()
        {
            int[] ports = BridgeServer.BuildCandidatePorts(17890, 10);

            Assert.AreEqual(10, ports.Length);
            Assert.AreEqual(17890, ports[0]);
            Assert.AreEqual(17899, ports[9]);
        }

        [Test]
        public void IsTokenValid_AcceptsExactMatch()
        {
            Assert.IsTrue(BridgeServer.IsTokenValid("abc123", "abc123"));
        }

        [Test]
        public void IsTokenValid_RejectsMismatch()
        {
            Assert.IsFalse(BridgeServer.IsTokenValid("wrong", "abc123"));
        }

        [Test]
        public void IsTokenValid_RejectsMissingProvidedToken()
        {
            Assert.IsFalse(BridgeServer.IsTokenValid(string.Empty, "abc123"));
            Assert.IsFalse(BridgeServer.IsTokenValid(null, "abc123"));
        }

        [Test]
        public void IsTokenValid_RejectsMissingExpectedToken()
        {
            Assert.IsFalse(BridgeServer.IsTokenValid("abc123", string.Empty));
        }

        [Test]
        public void ParseJsonOrNull_ReturnsNullForMalformedJson()
        {
            Assert.IsNull(BridgeServer.ParseJsonOrNull<OpenSceneRequest>("{not valid json"));
        }

        [Test]
        public void ParseJsonOrNull_ReturnsNullForEmptyBody()
        {
            Assert.IsNull(BridgeServer.ParseJsonOrNull<OpenSceneRequest>(string.Empty));
        }

        [Test]
        public void ParseJsonOrNull_ParsesValidJson()
        {
            OpenSceneRequest request = BridgeServer.ParseJsonOrNull<OpenSceneRequest>(
                @"{""scenePath"":""Assets/Scenes/Main.unity""}"
            );

            Assert.IsNotNull(request);
            Assert.AreEqual("Assets/Scenes/Main.unity", request.scenePath);
        }
    }
}
