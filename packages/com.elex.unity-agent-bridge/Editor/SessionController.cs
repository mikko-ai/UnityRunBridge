using System;
using System.IO;
using UnityEngine;

namespace Elex.UnityAgentBridge.Editor
{
    internal static class SessionController
    {
        private static string currentSessionId = string.Empty;
        private static string currentSessionPath = string.Empty;
        private static SessionLogWriter logWriter;

        public static bool HasActiveSession => logWriter != null;
        public static string CurrentSessionId => currentSessionId;
        public static string CurrentSessionPath => currentSessionPath;
        public static string CurrentLogPath => logWriter == null ? string.Empty : logWriter.LogPath;

        public static BridgeResponse StartSession(string sessionId, string sessionPath)
        {
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                return BridgeResponse.Failure("sessionId is required");
            }

            string projectRoot = GetProjectRoot();
            if (!IsAllowedSessionPath(projectRoot, sessionPath))
            {
                return BridgeResponse.Failure("sessionPath must be under <ProjectRoot>/.unity-agent/sessions");
            }

            EndSession();

            currentSessionId = sessionId;
            currentSessionPath = Path.GetFullPath(sessionPath);
            string logPath = Path.Combine(currentSessionPath, "unity-console.jsonl");
            logWriter = new SessionLogWriter(logPath);
            Application.logMessageReceived += OnLogMessageReceived;

            return new SessionStartResponse
            {
                ok = true,
                message = "session started",
                error = string.Empty,
                sessionId = currentSessionId,
                sessionPath = currentSessionPath,
                logPath = CurrentLogPath
            };
        }

        public static BridgeResponse EndSession()
        {
            if (logWriter == null)
            {
                currentSessionId = string.Empty;
                currentSessionPath = string.Empty;
                return BridgeResponse.Success("no active session");
            }

            Application.logMessageReceived -= OnLogMessageReceived;
            logWriter.Dispose();
            logWriter = null;
            currentSessionId = string.Empty;
            currentSessionPath = string.Empty;
            return BridgeResponse.Success("session ended");
        }

        public static SessionStatusResponse GetStatus()
        {
            return new SessionStatusResponse
            {
                ok = true,
                message = HasActiveSession ? "session active" : "no active session",
                error = string.Empty,
                hasActiveSession = HasActiveSession,
                sessionId = currentSessionId,
                sessionPath = currentSessionPath,
                logPath = CurrentLogPath
            };
        }

        public static bool IsAllowedSessionPath(string projectPath, string sessionPath)
        {
            if (string.IsNullOrWhiteSpace(projectPath) || string.IsNullOrWhiteSpace(sessionPath))
            {
                return false;
            }

            string projectFullPath = Normalize(Path.GetFullPath(projectPath));
            string sessionFullPath = Normalize(Path.GetFullPath(sessionPath));
            string allowedRoot = Normalize(Path.Combine(projectFullPath, ".unity-agent", "sessions"));
            return sessionFullPath.StartsWith(allowedRoot + "/", StringComparison.Ordinal);
        }

        private static void OnLogMessageReceived(string condition, string stackTrace, LogType type)
        {
            logWriter?.Write(condition, stackTrace, type);
        }

        private static string GetProjectRoot()
        {
            DirectoryInfo assetsDirectory = new DirectoryInfo(Application.dataPath);
            return assetsDirectory.Parent == null ? string.Empty : assetsDirectory.Parent.FullName;
        }

        private static string Normalize(string path)
        {
            return path.Replace('\\', '/').TrimEnd('/');
        }
    }
}
