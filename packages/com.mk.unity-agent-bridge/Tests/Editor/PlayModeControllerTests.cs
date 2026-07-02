using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests
{
    public sealed class PlayModeControllerTests
    {
        [Test]
        public void ValidateEnterPlayMode_WhenIdleAndCompiled_Accepts()
        {
            BridgeResponse response = PlayModeController.ValidateEnterPlayMode("idle", compilationSucceeded: true);

            Assert.IsTrue(response.ok);
            Assert.AreEqual("accepted", response.code);
        }

        [Test]
        public void ValidateEnterPlayMode_WhenAlreadyPlaying_ReturnsAlreadyPlaying()
        {
            BridgeResponse response = PlayModeController.ValidateEnterPlayMode("playing", compilationSucceeded: true);

            Assert.IsTrue(response.ok);
            Assert.AreEqual("already_playing", response.code);
        }

        [Test]
        public void ValidateEnterPlayMode_WhenNotIdle_ReturnsBusy()
        {
            BridgeResponse response = PlayModeController.ValidateEnterPlayMode("enteringPlay", compilationSucceeded: true);

            Assert.IsFalse(response.ok);
            Assert.AreEqual("busy", response.code);
        }

        [Test]
        public void ValidateEnterPlayMode_WhenCompilationFailed_ReturnsCompilationFailed()
        {
            BridgeResponse response = PlayModeController.ValidateEnterPlayMode("idle", compilationSucceeded: false);

            Assert.IsFalse(response.ok);
            Assert.AreEqual("compilation_failed", response.code);
        }
    }
}
