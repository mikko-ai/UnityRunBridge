using UnityEditor;
using Mk.UnityAgentBridge.Editor.Routing;

namespace Mk.UnityAgentBridge.Editor
{
    internal static class PlayModeController
    {
        public static BridgeResponse EnterPlayMode()
        {
            string editorState = EditorStateProvider.DeriveState(
                EditorApplication.isCompiling,
                EditorApplication.isUpdating,
                EditorApplication.isPlaying,
                EditorApplication.isPaused,
                EditorApplication.isPlayingOrWillChangePlaymode
            );
            BridgeResponse preflight = ValidateEnterPlayMode(editorState, CompilationTracker.LastCompilation.succeeded);
            if (!preflight.ok || preflight.code == "already_playing")
            {
                return preflight;
            }

            EditorApplication.isPlaying = true;
            return preflight;
        }

        public static BridgeResponse ExitPlayMode()
        {
            if (!EditorApplication.isPlaying)
            {
                return BridgeResponse.Success("already_stopped", "already stopped");
            }

            EditorApplication.isPlaying = false;
            return BridgeResponse.Success("accepted", "exiting play mode");
        }

        public static BridgeResponse Pause()
        {
            if (!EditorApplication.isPlaying)
            {
                return BridgeResponse.Failure("busy", "cannot pause when editor is not in play mode");
            }

            EditorApplication.isPaused = true;
            return BridgeResponse.Success("accepted", "paused");
        }

        public static BridgeResponse Resume()
        {
            if (!EditorApplication.isPlaying)
            {
                return BridgeResponse.Failure("busy", "cannot resume when editor is not in play mode");
            }

            EditorApplication.isPaused = false;
            return BridgeResponse.Success("accepted", "resumed");
        }

        internal static BridgeResponse ValidateEnterPlayMode(string editorState, bool compilationSucceeded)
        {
            if (editorState == "playing")
            {
                return BridgeResponse.Success("already_playing", "already in play mode");
            }

            if (editorState != "idle")
            {
                return BridgeResponse.Failure("busy", $"editor is not idle: {editorState}");
            }

            if (!compilationSucceeded)
            {
                return BridgeResponse.Failure("compilation_failed", "last compilation failed");
            }

            return BridgeResponse.Success("accepted", "entering play mode");
        }
    }
}
