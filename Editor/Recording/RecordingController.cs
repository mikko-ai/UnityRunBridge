using System;
using System.IO;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Mk.UnityAgentBridge.Editor.Recording
{
    /// <summary>
    /// 录制状态机 + 路由 handler。实际监听逻辑在 <see cref="RecordingListener"/>
    /// （EditorApplication.update 驱动的静态监听器），本类负责启停监听、落盘
    /// actions.jsonl / recording-meta.json，以及 domain reload / 退出 Play Mode 时
    /// 如实上报 "interrupted"（不静默丢失）。
    /// </summary>
    [InitializeOnLoad]
    internal static class RecordingController
    {
        internal const string StateIdle = "idle";
        internal const string StateRecording = "recording";
        internal const string StateInterrupted = "interrupted";

        private const string StateKey = "Mk.UnityAgentBridge.Recording.State";
        private const string ActionsPathKey = "Mk.UnityAgentBridge.Recording.ActionsPath";
        private const string MetaPathKey = "Mk.UnityAgentBridge.Recording.MetaPath";
        private const string ActionCountKey = "Mk.UnityAgentBridge.Recording.ActionCount";

        static RecordingController()
        {
            TempObjectRegistry.RegisterCleanupHandler(OnTempObjectCleanup);
        }

        public static void RegisterRoutes()
        {
            CapabilityRegistry.Declare("recording");
            RouteTable.Register("POST", "recording/start", Start);
            RouteTable.Register("POST", "recording/stop", Stop);
            RouteTable.Register("GET", "recording/status", Status);
        }

        internal static object Start(BridgeRequestContext ctx)
        {
            string editorState = CurrentEditorState();
            if (editorState != "playing")
            {
                return BridgeResponse.Failure("not_in_play_mode", $"该操作需要 Play Mode（当前 editorState={editorState}）");
            }

            if (CurrentState() == StateRecording)
            {
                return BridgeResponse.Failure("already_recording", "已经在录制中，请先调用 POST /recording/stop");
            }

            if (!RecordingListener.HasInputBackend)
            {
                return BridgeResponse.Failure(
                    "no_input_backend", "项目未启用任何受支持的输入后端（Input Manager 或 Input System）");
            }

            JsonValue body = ctx.Body;
            string targetDirectoryRaw = body != null && body.TryGetString("targetDirectory", out string dirValue)
                ? dirValue
                : null;

            string projectRoot = ArtifactPathGuard.GetProjectRoot();
            string targetDirectory = string.IsNullOrWhiteSpace(targetDirectoryRaw)
                ? ArtifactPathGuard.ResolveArtifactDirectory()
                : targetDirectoryRaw;

            if (!ArtifactPathGuard.IsAllowedArtifactPath(projectRoot, targetDirectory))
            {
                return BridgeResponse.Failure(
                    "invalid_argument", "targetDirectory must be under .unity-agent/sessions or .unity-agent/scratch");
            }

            Directory.CreateDirectory(targetDirectory);
            string actionsPath = Path.Combine(targetDirectory, "actions.jsonl");
            string metaPath = Path.Combine(targetDirectory, "recording-meta.json");

            WriteMeta(metaPath);
            // 覆盖式创建：同名旧文件会被截断，避免把上一次录制的动作和这一次混在一起。
            File.WriteAllText(actionsPath, string.Empty);

            RecordingListener.StartListening(action => AppendAction(actionsPath, action));

            SessionState.SetString(StateKey, StateRecording);
            SessionState.SetString(ActionsPathKey, actionsPath);
            SessionState.SetString(MetaPathKey, metaPath);
            SessionState.SetInt(ActionCountKey, 0);

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["actionsPath"] = actionsPath;
            response["metaPath"] = metaPath;
            return response;
        }

        internal static object Stop(BridgeRequestContext ctx)
        {
            string state = CurrentState();
            if (state == StateIdle)
            {
                JsonValue idleResponse = JsonValue.NewObject();
                idleResponse["ok"] = true;
                idleResponse["code"] = "not_recording";
                idleResponse["actionsPath"] = JsonValue.Null;
                idleResponse["actionCount"] = 0;
                idleResponse["interrupted"] = false;
                return idleResponse;
            }

            string actionsPath = SessionState.GetString(ActionsPathKey, string.Empty);
            int actionCount = SessionState.GetInt(ActionCountKey, 0);
            bool wasInterrupted = state == StateInterrupted;

            RecordingListener.StopListening();
            SessionState.SetString(StateKey, StateIdle);
            SessionState.EraseString(ActionsPathKey);
            SessionState.EraseString(MetaPathKey);
            SessionState.EraseInt(ActionCountKey);

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["actionsPath"] = actionsPath;
            response["actionCount"] = actionCount;
            response["interrupted"] = wasInterrupted;
            return response;
        }

        internal static object Status(BridgeRequestContext ctx)
        {
            string state = CurrentState();

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["recording"] = state == StateRecording;
            response["interrupted"] = state == StateInterrupted;
            response["actionCount"] = SessionState.GetInt(ActionCountKey, 0);
            response["actionsPath"] = state == StateIdle
                ? JsonValue.Null
                : JsonValue.FromString(SessionState.GetString(ActionsPathKey, string.Empty));
            return response;
        }

        internal static string CurrentState() => SessionState.GetString(StateKey, StateIdle);

        /// <summary>仅供 EditMode 测试使用：模拟 domain reload / 退出 Play Mode 打断录制，
        /// 不必真的触发 TempObjectRegistry 的三个生产环境钩子。</summary>
        internal static void SimulateInterruptionForTests(string reason) => OnTempObjectCleanup(reason);

        /// <summary>仅供 EditMode 测试使用：把状态机重置为 idle，避免测试之间通过
        /// SessionState 互相污染（SessionState 在同一 Editor 会话内跨测试持久存在）。</summary>
        internal static void ResetForTests()
        {
            RecordingListener.ResetForTests();
            SessionState.EraseString(StateKey);
            SessionState.EraseString(ActionsPathKey);
            SessionState.EraseString(MetaPathKey);
            SessionState.EraseInt(ActionCountKey);
        }

        private static void AppendAction(string actionsPath, RecordedAction action)
        {
            JsonValue json = JsonValue.NewObject();
            json["time"] = action.Time;
            json["frame"] = action.Frame;
            json["type"] = action.Type;
            json["scene"] = action.Scene;
            json["path"] = action.Path;

            if (action.Type == "click")
            {
                JsonValue screenPos = JsonValue.NewObject();
                screenPos["x"] = action.ScreenX;
                screenPos["y"] = action.ScreenY;
                json["screenPos"] = screenPos;
            }
            else if (action.Type == "input")
            {
                json["text"] = action.Text ?? string.Empty;
            }

            try
            {
                File.AppendAllText(actionsPath, json.ToString() + "\n");
                SessionState.SetInt(ActionCountKey, SessionState.GetInt(ActionCountKey, 0) + 1);
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"Unity Agent Bridge: 写入 actions.jsonl 失败：{ex.Message}");
            }
        }

        private static void WriteMeta(string metaPath)
        {
            JsonValue meta = JsonValue.NewObject();
            meta["schemaVersion"] = 1;
            meta["startedAt"] = DateTime.UtcNow.ToString("O");
            meta["activeScene"] = SceneManager.GetActiveScene().name;

            JsonValue loadedScenes = JsonValue.NewArray();
            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                loadedScenes.Add(SceneManager.GetSceneAt(i).name);
            }

            meta["loadedScenes"] = loadedScenes;

            JsonValue screenSize = JsonValue.NewObject();
            screenSize["w"] = Screen.width;
            screenSize["h"] = Screen.height;
            meta["screenSize"] = screenSize;

            meta["sessionId"] = SessionController.CurrentSessionId ?? string.Empty;

            File.WriteAllText(metaPath, meta.ToString());
        }

        /// <summary>
        /// domain reload 会连带清空 RecordingListener 的静态订阅状态；退出 Play Mode / Editor 退出
        /// 则显式调用 StopListening() 停止轮询。三种情况下都如实把状态标记为 interrupted，
        /// 而不是让下一次 status/stop 误以为仍在正常录制或静默丢弃已录制的动作。
        /// </summary>
        private static void OnTempObjectCleanup(string reason)
        {
            RecordingListener.StopListening();
            if (CurrentState() == StateRecording)
            {
                SessionState.SetString(StateKey, StateInterrupted);
            }
        }

        private static string CurrentEditorState()
        {
            return EditorStateProvider.DeriveState(
                EditorApplication.isCompiling,
                EditorApplication.isUpdating,
                EditorApplication.isPlaying,
                EditorApplication.isPaused,
                EditorApplication.isPlayingOrWillChangePlaymode);
        }
    }
}
