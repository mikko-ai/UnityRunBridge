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
        private const string RunIndexKey = "Mk.UnityAgentBridge.RunIndex";

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
        private static int runIndex;

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
            // session 在 Play Mode 进行中启动（如 play 收到 already_playing）时，把正在进行的这一轮记为 run 1。
            runIndex = EditorApplication.isPlaying ? 1 : 0;
            logWriter = new SessionLogWriter(logPath);
            Application.logMessageReceived += OnLogMessageReceived;
            EditorApplication.playModeStateChanged += OnPlayModeStateChanged;
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
            EditorApplication.playModeStateChanged -= OnPlayModeStateChanged;
            logWriter.Dispose();
            logWriter = null;
            currentSessionId = string.Empty;
            currentSessionPath = string.Empty;
            sequence = 0;
            runIndex = 0;
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
            runIndex = SessionState.GetInt(RunIndexKey, 0);
            logWriter = new SessionLogWriter(logPath);
            Application.logMessageReceived -= OnLogMessageReceived;
            Application.logMessageReceived += OnLogMessageReceived;
            EditorApplication.playModeStateChanged -= OnPlayModeStateChanged;
            EditorApplication.playModeStateChanged += OnPlayModeStateChanged;
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
            logWriter.Write(condition, stackTrace, type, sequence, runIndex);
            SessionState.SetInt(SequenceKey, sequence);
        }

        /// <summary>
        /// Play Mode 运行边界：会话生命周期与 Play Mode 保持解耦——手动进/退 Play 不结束
        /// 会话，但每一轮运行的边界与轮次（runIndex）会如实落进 unity-console.jsonl，
        /// 供 CLI 侧按轮分组与人工干预检测（一个 session 内 CLI 只触发一轮 play，
        /// runIndex >= 2 即存在手动干预）。
        ///
        /// 时机选择：
        /// - runStarted 用 ExitingEditMode（进 Play 流程开始、domain reload 之前）——
        ///   EnteredPlayMode 在 Awake 之后才触发，若在那里递增会把新一轮的 reload 噪音
        ///   与 Awake 日志错标到上一轮；runIndex 递增后立即持久化，reload 后由
        ///   RestoreActiveSession 恢复。
        /// - runEnded 用 EnteredEditMode（退出流程完全结束）——ExitingPlayMode 时
        ///   OnDestroy 日志尚未产生，过早收尾会把它们排除在本轮之外。
        /// </summary>
        private static void OnPlayModeStateChanged(PlayModeStateChange change)
        {
            if (logWriter == null)
            {
                return;
            }

            if (change == PlayModeStateChange.ExitingEditMode)
            {
                runIndex += 1;
                SessionState.SetInt(RunIndexKey, runIndex);
                WriteBoundaryEvent("runStarted");
            }
            else if (change == PlayModeStateChange.EnteredEditMode)
            {
                WriteBoundaryEvent("runEnded");
            }
        }

        private static void WriteBoundaryEvent(string eventName)
        {
            sequence += 1;
            logWriter.WriteEvent(eventName, sequence, runIndex);
            SessionState.SetInt(SequenceKey, sequence);
        }

        private static void RememberSession(string sessionId, string sessionPath)
        {
            SessionState.SetString(SessionIdKey, sessionId);
            SessionState.SetString(SessionPathKey, sessionPath);
            SessionState.SetInt(SequenceKey, sequence);
            SessionState.SetInt(RunIndexKey, runIndex);
        }

        private static void ForgetSession()
        {
            SessionState.EraseString(SessionIdKey);
            SessionState.EraseString(SessionPathKey);
            SessionState.EraseInt(SequenceKey);
            SessionState.EraseInt(RunIndexKey);
        }

        private static string GetProjectRoot()
        {
            return ArtifactPathGuard.GetProjectRoot();
        }
    }
}
