using UnityEditor;

namespace Mk.UnityAgentBridge.Editor.Capture
{
    /// <summary>
    /// maxPerSession 配额计数：以当前 session（无 session 时退化为固定 "scratch" 键）为维度，
    /// 持久于 SessionState（跨 domain reload 不重置，与其它 job/session 状态一致）。
    /// </summary>
    internal static class CaptureQuota
    {
        private const string KeyPrefix = "Mk.UnityAgentBridge.CaptureQuota.";

        public static bool TryConsume(string kind, int maxPerSession, out int usedCount)
        {
            string key = BuildKey(kind);
            int current = SessionState.GetInt(key, 0);
            if (current >= maxPerSession)
            {
                usedCount = current;
                return false;
            }

            usedCount = current + 1;
            SessionState.SetInt(key, usedCount);
            return true;
        }

        internal static void ResetForTests(string kind)
        {
            SessionState.EraseInt(BuildKey(kind));
        }

        private static string BuildKey(string kind)
        {
            string scope = SessionController.HasActiveSession ? SessionController.CurrentSessionId : "scratch";
            return $"{KeyPrefix}{kind}.{scope}";
        }
    }
}
