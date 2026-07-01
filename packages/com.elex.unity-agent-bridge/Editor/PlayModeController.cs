using UnityEditor;

namespace Elex.UnityAgentBridge.Editor
{
    internal static class PlayModeController
    {
        public static BridgeResponse EnterPlayMode()
        {
            if (EditorApplication.isPlaying)
            {
                return BridgeResponse.Success("already in play mode");
            }

            if (EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                return BridgeResponse.Failure("editor is compiling or updating");
            }

            EditorApplication.isPlaying = true;
            return BridgeResponse.Success("entering play mode");
        }

        public static BridgeResponse ExitPlayMode()
        {
            if (!EditorApplication.isPlaying)
            {
                return BridgeResponse.Success("already stopped");
            }

            EditorApplication.isPlaying = false;
            return BridgeResponse.Success("exiting play mode");
        }

        public static BridgeResponse Pause()
        {
            if (!EditorApplication.isPlaying)
            {
                return BridgeResponse.Failure("cannot pause when editor is not in play mode");
            }

            EditorApplication.isPaused = true;
            return BridgeResponse.Success("paused");
        }

        public static BridgeResponse Resume()
        {
            if (!EditorApplication.isPlaying)
            {
                return BridgeResponse.Failure("cannot resume when editor is not in play mode");
            }

            EditorApplication.isPaused = false;
            return BridgeResponse.Success("resumed");
        }
    }
}
