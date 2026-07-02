using System;
using System.Collections.Generic;

namespace Mk.UnityAgentBridge.Editor
{
    [Serializable]
    public class BridgeResponse
    {
        public bool ok;
        public string code;
        public string message;

        public static BridgeResponse Success(string code, string message)
        {
            return new BridgeResponse
            {
                ok = true,
                code = code,
                message = message
            };
        }

        public static BridgeResponse Failure(string code, string message)
        {
            return new BridgeResponse
            {
                ok = false,
                code = code,
                message = message
            };
        }
    }

    [Serializable]
    public sealed class CompilationErrorEntry
    {
        public string file;
        public int line;
        public string message;
    }

    [Serializable]
    public sealed class BridgeStatusResponse : BridgeResponse
    {
        public string bridgeVersion;
        public string unityVersion;
        public string editorState;
        public bool isPlaying;
        public bool isPaused;
        public bool isCompiling;
        public bool isUpdating;
        public bool willEnterPlayMode;
        public string activeScenePath;
        public bool compilationSucceeded;
        public string compilationFinishedAt;
        public List<CompilationErrorEntry> compilationErrors;
        public bool hasActiveSession;
        public string sessionId;
        public string sessionPath;
        public string logPath;
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
