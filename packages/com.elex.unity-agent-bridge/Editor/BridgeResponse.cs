using System;

namespace Elex.UnityAgentBridge.Editor
{
    [Serializable]
    public class BridgeResponse
    {
        public bool ok;
        public string message;
        public string error;

        public static BridgeResponse Success(string message)
        {
            return new BridgeResponse
            {
                ok = true,
                message = message,
                error = string.Empty
            };
        }

        public static BridgeResponse Failure(string error)
        {
            return new BridgeResponse
            {
                ok = false,
                message = string.Empty,
                error = error
            };
        }
    }

    [Serializable]
    public sealed class BridgeStatusResponse : BridgeResponse
    {
        public string bridgeVersion;
        public string unityVersion;
        public string activeScenePath;
        public bool isPlaying;
        public bool isPaused;
        public bool isCompiling;
        public bool isUpdating;
    }

    [Serializable]
    public sealed class OpenSceneRequest
    {
        public string scenePath;
    }

    [Serializable]
    public sealed class SessionStartRequest
    {
        public string sessionId;
        public string sessionPath;
    }

    [Serializable]
    public sealed class SessionStartResponse : BridgeResponse
    {
        public string sessionId;
        public string sessionPath;
        public string logPath;
    }

    [Serializable]
    public sealed class SessionStatusResponse : BridgeResponse
    {
        public bool hasActiveSession;
        public string sessionId;
        public string sessionPath;
        public string logPath;
    }
}
