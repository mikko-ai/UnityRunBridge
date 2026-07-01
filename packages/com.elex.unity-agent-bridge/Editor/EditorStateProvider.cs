using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Elex.UnityAgentBridge.Editor
{
    internal static class EditorStateProvider
    {
        public static BridgeStatusResponse GetStatus()
        {
            return new BridgeStatusResponse
            {
                ok = true,
                message = "ready",
                error = string.Empty,
                bridgeVersion = BridgeConfig.Version,
                unityVersion = Application.unityVersion,
                activeScenePath = EditorSceneManager.GetActiveScene().path,
                isPlaying = EditorApplication.isPlaying,
                isPaused = EditorApplication.isPaused,
                isCompiling = EditorApplication.isCompiling,
                isUpdating = EditorApplication.isUpdating
            };
        }
    }
}
