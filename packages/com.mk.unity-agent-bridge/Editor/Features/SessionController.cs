using Mk.UnityAgentBridge.Editor.Routing;

namespace Mk.UnityAgentBridge.Editor
{
    /// <summary>
    /// Session 路由登记与薄转发（Phase 1）：状态与生命周期逻辑已下沉到 Core 的
    /// <see cref="SessionService"/>，本类只负责注册 HTTP 路由并转发到服务，
    /// 兼容仍引用 SessionController 静态成员的旧代码与测试。status JSON 字段保持不变。
    /// </summary>
    internal static class SessionController
    {
        public static bool HasActiveSession => SessionService.HasActiveSession;
        public static string CurrentSessionId => SessionService.CurrentSessionId;
        public static string CurrentSessionPath => SessionService.CurrentSessionPath;
        public static string CurrentLogPath => SessionService.CurrentLogPath;

        public static BridgeResponse StartSession(string sessionId, string sessionPath) =>
            SessionService.StartSession(sessionId, sessionPath);

        public static BridgeResponse EndSession() => SessionService.EndSession();

        public static void RestoreActiveSession() => SessionService.RestoreActiveSession();

        public static SessionStatusResponse GetStatus() => SessionService.GetStatus();

        public static bool IsAllowedSessionPath(string projectPath, string sessionPath) =>
            SessionService.IsAllowedSessionPath(projectPath, sessionPath);
    }
}
