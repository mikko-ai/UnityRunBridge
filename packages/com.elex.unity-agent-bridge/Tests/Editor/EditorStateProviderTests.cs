using NUnit.Framework;

namespace Elex.UnityAgentBridge.Editor.Tests
{
    public sealed class EditorStateProviderTests
    {
        [Test]
        public void GetStatus_ReturnsBridgeStatus()
        {
            BridgeStatusResponse status = EditorStateProvider.GetStatus();

            Assert.IsTrue(status.ok);
            Assert.AreEqual("0.1.0", status.bridgeVersion);
            Assert.IsNotEmpty(status.unityVersion);
            Assert.IsNotNull(status.activeScenePath);
        }
    }
}
