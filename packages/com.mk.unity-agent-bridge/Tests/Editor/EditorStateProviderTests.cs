using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests
{
    public sealed class EditorStateProviderTests
    {
        [Test]
        public void GetStatus_ReturnsBridgeStatus()
        {
            BridgeStatusResponse status = EditorStateProvider.GetStatus();

            Assert.IsTrue(status.ok);
            Assert.AreEqual("ok", status.code);
            Assert.AreEqual("0.1.0", status.bridgeVersion);
            Assert.IsNotEmpty(status.unityVersion);
            Assert.IsNotNull(status.activeScenePath);
            Assert.IsNotNull(status.editorState);
        }

        [Test]
        public void DeriveState_Compiling_TakesPriorityOverEverything()
        {
            Assert.AreEqual(
                "compiling",
                EditorStateProvider.DeriveState(isCompiling: true, isUpdating: true, isPlaying: true, isPaused: true, willChangePlaymode: true)
            );
        }

        [Test]
        public void DeriveState_Updating_TakesPriorityOverPlayState()
        {
            Assert.AreEqual(
                "updating",
                EditorStateProvider.DeriveState(isCompiling: false, isUpdating: true, isPlaying: true, isPaused: true, willChangePlaymode: true)
            );
        }

        [Test]
        public void DeriveState_PlayingAndPaused_IsPaused()
        {
            Assert.AreEqual(
                "paused",
                EditorStateProvider.DeriveState(isCompiling: false, isUpdating: false, isPlaying: true, isPaused: true, willChangePlaymode: true)
            );
        }

        [Test]
        public void DeriveState_PlayingAndNotWillChange_IsExitingPlay()
        {
            Assert.AreEqual(
                "exitingPlay",
                EditorStateProvider.DeriveState(isCompiling: false, isUpdating: false, isPlaying: true, isPaused: false, willChangePlaymode: false)
            );
        }

        [Test]
        public void DeriveState_Playing_IsPlaying()
        {
            Assert.AreEqual(
                "playing",
                EditorStateProvider.DeriveState(isCompiling: false, isUpdating: false, isPlaying: true, isPaused: false, willChangePlaymode: true)
            );
        }

        [Test]
        public void DeriveState_WillChangeButNotPlayingYet_IsEnteringPlay()
        {
            Assert.AreEqual(
                "enteringPlay",
                EditorStateProvider.DeriveState(isCompiling: false, isUpdating: false, isPlaying: false, isPaused: false, willChangePlaymode: true)
            );
        }

        [Test]
        public void DeriveState_NoFlagsSet_IsIdle()
        {
            Assert.AreEqual(
                "idle",
                EditorStateProvider.DeriveState(isCompiling: false, isUpdating: false, isPlaying: false, isPaused: false, willChangePlaymode: false)
            );
        }
    }
}
