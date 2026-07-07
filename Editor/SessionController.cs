using System.IO;
using UnityEditor;
using UnityEngine;
using Mk.UnityAgentBridge.Editor.Routing;

namespace Mk.UnityAgentBridge.Editor
{
    internal static class SessionController
    {
        private const string SessionIdKey = "Mk.UnityAgentBridge.SessionId";
        private const string SessionPathKey = "Mk.UnityAgentBridge.SessionPath";
        private const string SequenceKey = "Mk.UnityAgentBridge.LogSequence";

        public static void RegisterRoutes()
        {
            RouteTable.Register("POST", "session/start", ctx =>
            {
                SessionStartRequest sessionRequest = BridgeServer.ParseJsonOrNull<SessionStartRequest>(ctx.RawBody);
                if (sessionRequest == null)
                {
                    return BridgeResponse.Failure("invalid_request", "invalid session start request");
                }

                return StartSession(sessionRequest.sessionId, sessionRequest.sessionPath);
            });
            RouteTable.Register("POST", "session/end", ctx => EndSession());
            RouteTable.Register("GET", "session/status", ctx => GetStatus());
        }

        private static string currentSessionId = string.Empty;
        private static string currentSessionPath = string.Empty;
        private static SessionLogWriter logWriter;
        private static int sequence;

        public static bool HasActiveSession => logWriter != null;
        public static string CurrentSessionId => currentSessionId;
        public static string CurrentSessionPath => currentSessionPath;
        public static string CurrentLogPath => logWriter == null ? string.Empty : logWriter.LogPath;

        public static BridgeResponse StartSession(string sessionId, string sessionPath)
        {
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                return BridgeResponse.Failure("invalid_request", "sessionId is required");
            }

            string projectRoot = GetProjectRoot();
            if (!IsAllowedSessionPath(projectRoot, sessionPath))
            {
                return BridgeResponse.Failure("invalid_request", "sessionPath must be under <ProjectRoot>/.unity-agent/sessions");
            }

            EndSession();

            currentSessionId = sessionId;
            currentSessionPath = Path.GetFullPath(sessionPath);
            string logPath = Path.Combine(currentSessionPath, "unity-console.jsonl");
            sequence = 0;
            logWriter = new SessionLogWriter(logPath);
            Application.logMessageReceived += OnLogMessageReceived;
            RememberSession(currentSessionId, currentSessionPath);

            return new SessionStartResponse
            {
                ok = true,
                code = "session_started",
                message = "session started",
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
                ForgetSession();
                return BridgeResponse.Success("no_active_session", "no active session");
            }

            Application.logMessageReceived -= OnLogMessageReceived;
            logWriter.Dispose();
            logWriter = null;
            currentSessionId = string.Empty;
            currentSessionPath = string.Empty;
            sequence = 0;
            ForgetSession();
            return BridgeResponse.Success("session_ended", "session ended");
        }

        public static void RestoreActiveSession()
        {
            if (logWriter != null)
            {
                return;
            }

            string sessionId = SessionState.GetString(SessionIdKey, string.Empty);
            string sessionPath = SessionState.GetString(SessionPathKey, string.Empty);
            if (string.IsNullOrWhiteSpace(sessionId) || string.IsNullOrWhiteSpace(sessionPath))
            {
                return;
            }

            string projectRoot = GetProjectRoot();
            if (!IsAllowedSessionPath(projectRoot, sessionPath))
            {
                ForgetSession();
                return;
            }

            currentSessionId = sessionId;
            currentSessionPath = Path.GetFullPath(sessionPath);
            string logPath = Path.Combine(currentSessionPath, "unity-console.jsonl");
            sequence = SessionState.GetInt(SequenceKey, 0);
            logWriter = new SessionLogWriter(logPath);
            Application.logMessageReceived -= OnLogMessageReceived;
            Application.logMessageReceived += OnLogMessageReceived;
        }

        public static SessionStatusResponse GetStatus()
        {
            return new SessionStatusResponse
            {
                ok = true,
                code = "ok",
                message = HasActiveSession ? "session active" : "no active session",
                hasActiveSession = HasActiveSession,
                sessionId = currentSessionId,
                sessionPath = currentSessionPath,
                logPath = CurrentLogPath
            };
        }

        public static bool IsAllowedSessionPath(string projectPath, string sessionPath)
        {
            return ArtifactPathGuard.IsAllowedSessionPath(projectPath, sessionPath);
        }

        private static void OnLogMessageReceived(string condition, string stackTrace, LogType type)
        {
            if (logWriter == null)
            {
                return;
            }

            sequence += 1;
            logWriter.Write(condition, stackTrace, type, sequence);
            SessionState.SetInt(SequenceKey, sequence);
        }

        private static void RememberSession(string sessionId, string sessionPath)
        {
            SessionState.SetString(SessionIdKey, sessionId);
            SessionState.SetString(SessionPathKey, sessionPath);
            SessionState.SetInt(SequenceKey, sequence);
        }

        private static void ForgetSession()
        {
            SessionState.EraseString(SessionIdKey);
            SessionState.EraseString(SessionPathKey);
            SessionState.EraseInt(SequenceKey);
        }

        private static string GetProjectRoot()
        {
            return ArtifactPathGuard.GetProjectRoot();
        }
    }
}
