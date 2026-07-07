using System;
using UnityEditor.SceneManagement;
using Mk.UnityAgentBridge.Editor.Routing;

namespace Mk.UnityAgentBridge.Editor
{
    internal static class SceneController
    {
        public static void RegisterRoutes()
        {
            RouteTable.Register("POST", "open-scene", ctx =>
            {
                OpenSceneRequest sceneRequest = BridgeServer.ParseJsonOrNull<OpenSceneRequest>(ctx.RawBody);
                if (sceneRequest == null)
                {
                    return BridgeResponse.Failure("invalid_request", "invalid open-scene request body");
                }

                return OpenScene(sceneRequest.scenePath);
            });
        }

        public static BridgeResponse OpenScene(string scenePath)
        {
            if (!IsValidProjectScenePath(scenePath))
            {
                return BridgeResponse.Failure("invalid_request", "scenePath must be a Unity scene under Assets");
            }

            try
            {
                EditorSceneManager.OpenScene(scenePath);
                return BridgeResponse.Success("accepted", "scene opened");
            }
            catch (Exception ex)
            {
                return BridgeResponse.Failure("internal_error", ex.Message);
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
