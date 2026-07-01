using System;
using UnityEditor.SceneManagement;

namespace Elex.UnityAgentBridge.Editor
{
    internal static class SceneController
    {
        public static BridgeResponse OpenScene(string scenePath)
        {
            if (!IsValidProjectScenePath(scenePath))
            {
                return BridgeResponse.Failure("scenePath must be a Unity scene under Assets");
            }

            try
            {
                EditorSceneManager.OpenScene(scenePath);
                return BridgeResponse.Success("scene opened");
            }
            catch (Exception ex)
            {
                return BridgeResponse.Failure(ex.Message);
            }
        }

        public static bool IsValidProjectScenePath(string scenePath)
        {
            if (string.IsNullOrWhiteSpace(scenePath))
            {
                return false;
            }

            string normalized = scenePath.Replace('\\', '/');
            return normalized.StartsWith("Assets/", StringComparison.Ordinal)
                && normalized.EndsWith(".unity", StringComparison.OrdinalIgnoreCase)
                && !normalized.Contains("../", StringComparison.Ordinal);
        }
    }
}
