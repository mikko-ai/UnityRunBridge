using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor
{
    public static class EditorStateProvider
    {
        public static BridgeStatusResponse GetStatus()
        {
            bool isPlaying = EditorApplication.isPlaying;
            bool isPaused = EditorApplication.isPaused;
            bool isCompiling = EditorApplication.isCompiling;
            bool isUpdating = EditorApplication.isUpdating;
            bool willChangePlaymode = EditorApplication.isPlayingOrWillChangePlaymode;

            CompilationTracker.LastCompilationInfo lastCompilation = CompilationTracker.LastCompilation;

            return new BridgeStatusResponse
            {
                ok = true,
                code = "ok",
                message = "ready",
                bridgeVersion = BridgeConfig.Version,
                unityVersion = Application.unityVersion,
                editorState = DeriveState(isCompiling, isUpdating, isPlaying, isPaused, willChangePlaymode),
                isPlaying = isPlaying,
                isPaused = isPaused,
                isCompiling = isCompiling,
                isUpdating = isUpdating,
                willEnterPlayMode = willChangePlaymode && !isPlaying,
                activeScenePath = EditorSceneManager.GetActiveScene().path,
                compilationSucceeded = lastCompilation.succeeded,
                compilationFinishedAt = lastCompilation.finishedAt,
                compilationErrors = lastCompilation.errors,
                hasActiveSession = SessionService.HasActiveSession,
                sessionId = SessionService.CurrentSessionId,
                sessionPath = SessionService.CurrentSessionPath,
                logPath = SessionService.CurrentLogPath
            };
        }

        /// <summary>
        /// 纯函数：按固定优先级把原始 Editor 标志位派生成单一的 editorState 字符串，
        /// 便于 EditMode 测试覆盖全部分支，也便于 CLI 的收敛循环基于单一字段判断。
        /// </summary>
        public static string DeriveState(bool isCompiling, bool isUpdating, bool isPlaying, bool isPaused, bool willChangePlaymode)
        {
            if (isCompiling)
            {
                return "compiling";
            }

            if (isUpdating)
            {
                return "updating";
            }

            if (isPlaying && isPaused)
            {
                return "paused";
            }

            if (isPlaying && !willChangePlaymode)
            {
                return "exitingPlay";
            }

            if (isPlaying)
            {
                return "playing";
            }

            if (willChangePlaymode && !isPlaying)
            {
                return "enteringPlay";
            }

            return "idle";
        }
    }
}
