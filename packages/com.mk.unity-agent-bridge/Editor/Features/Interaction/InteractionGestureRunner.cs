using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Interaction
{
    /// <summary>
    /// 跨帧手势执行器：同一时间仅允许一个手势（single-flight），
    /// 由 EditorApplication.update 推进，结果写入 JobManager。
    /// 退出 Play Mode / Domain Reload / 超时必须释放 pointer 状态。
    /// </summary>
    internal static class InteractionGestureRunner
    {
        private const double MaxGestureDurationSeconds = 3600.0;
        private const int MaxGestureSteps = 4096;
        private static ActiveGesture active;
        private static bool subscribed;

        private sealed class ActiveGesture
        {
            public JobHandle Handle;
            public InteractionGestureSession Session;
            public IInteractionGestureBackend Backend;
        }

        internal static object StartLongPress(BridgeRequestContext ctx, IBridgeServiceResolver services = null)
        {
            services = BridgeServices.Current(services);
            JsonValue body = ctx.Body;
            if (body == null || !body.TryGetString("path", out string path))
            {
                return BridgeResponse.Failure("invalid_argument", "body 必须包含字符串字段 path");
            }

            double duration = body.TryGetDouble("durationSeconds", out double durationValue)
                ? durationValue
                : 0.5;
            if (!IsFinite(duration) || duration <= 0 || duration > MaxGestureDurationSeconds)
            {
                return BridgeResponse.Failure(
                    "invalid_argument",
                    $"durationSeconds 必须为有限正数且不超过 {MaxGestureDurationSeconds} 秒");
            }

            float durationSeconds = (float)duration;
            bool force = body.GetBoolean("force", false);
            string scene = body.TryGetString("scene", out string sceneValue) ? sceneValue : null;

            return StartGesture(
                services,
                kind: "long-press",
                path: path,
                scene: scene,
                timeoutSeconds: Math.Max(2.0, durationSeconds + 5.0),
                begin: (backend, target) => backend.BeginLongPress(target, durationSeconds, force));
        }

        internal static object StartDrag(BridgeRequestContext ctx, IBridgeServiceResolver services = null)
        {
            services = BridgeServices.Current(services);
            JsonValue body = ctx.Body;
            if (body == null || !body.TryGetString("path", out string path))
            {
                return BridgeResponse.Failure("invalid_argument", "body 必须包含字符串字段 path");
            }

            if (!body.TryGetDouble("deltaX", out double deltaX) ||
                !body.TryGetDouble("deltaY", out double deltaY))
            {
                return BridgeResponse.Failure("invalid_argument", "body 必须包含数值字段 deltaX、deltaY");
            }

            if (!IsFiniteFloat(deltaX) || !IsFiniteFloat(deltaY))
            {
                return BridgeResponse.Failure("invalid_argument", "deltaX/deltaY 必须是 float 范围内的有限数值");
            }

            double duration = body.TryGetDouble("durationSeconds", out double durationValue)
                ? durationValue
                : 0.3;
            if (!IsFinite(duration) || duration <= 0 || duration > MaxGestureDurationSeconds)
            {
                return BridgeResponse.Failure(
                    "invalid_argument",
                    $"durationSeconds 必须为有限正数且不超过 {MaxGestureDurationSeconds} 秒");
            }

            double stepValue = 8;
            if (body.TryGet("steps", out JsonValue stepJson))
            {
                if (!stepJson.IsNumber)
                {
                    return BridgeResponse.Failure("invalid_argument", "steps 必须为整数");
                }

                stepValue = stepJson.AsDouble;
            }

            if (!IsFinite(stepValue) ||
                stepValue != Math.Truncate(stepValue) ||
                stepValue < 1 ||
                stepValue > MaxGestureSteps)
            {
                return BridgeResponse.Failure(
                    "invalid_argument",
                    $"steps 必须是 1 到 {MaxGestureSteps} 之间的整数");
            }

            float durationSeconds = (float)duration;
            int steps = (int)stepValue;
            bool force = body.GetBoolean("force", false);
            string scene = body.TryGetString("scene", out string sceneValue) ? sceneValue : null;

            return StartGesture(
                services,
                kind: "drag",
                path: path,
                scene: scene,
                timeoutSeconds: Math.Max(2.0, durationSeconds + 5.0),
                begin: (backend, target) => backend.BeginDrag(
                    target, (float)deltaX, (float)deltaY, durationSeconds, steps, force));
        }

        private static object StartGesture(
            IBridgeServiceResolver services,
            string kind,
            string path,
            string scene,
            double timeoutSeconds,
            Func<IInteractionGestureBackend, GameObject, InteractionGestureSession> begin)
        {
            if (!TryValidatePlayMode(out BridgeResponse rejection))
            {
                return rejection;
            }

            if (active != null)
            {
                return BridgeResponse.Failure("interaction_busy", "已有手势正在执行，同一时间仅允许一个手势");
            }

            if (services == null || !services.TryGet(out IInteractionGestureBackend backend))
            {
                return BridgeResponse.Failure(
                    "bridge_capability_missing",
                    "当前 Bridge 未提供 IInteractionGestureBackend（通常表示无 UGUI Adapter）");
            }

            NodePath.ResolveResult resolved = NodePath.Resolve(path, scene);
            if (!resolved.Ok)
            {
                return BridgeResponse.Failure(resolved.ErrorCode, resolved.ErrorMessage);
            }

            InteractionGestureSession session = begin(backend, resolved.Node.gameObject);

            // 同步失败（无 EventSystem / 遮挡等）直接返回，不启 job
            if (session.Completed)
            {
                return MapCompletedSession(session);
            }

            JobStartResult start = JobManager.StartJob(kind, handle =>
            {
                active = new ActiveGesture
                {
                    Handle = handle,
                    Session = session,
                    Backend = backend
                };
                EnsureSubscribed();
            }, timeoutSeconds);

            if (!start.Ok)
            {
                backend.Cancel(session);
                return BridgeResponse.Failure(start.ErrorCode, start.ErrorMessage);
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["jobId"] = start.JobId;
            return response;
        }

        private static void EnsureSubscribed()
        {
            if (subscribed)
            {
                return;
            }

            EditorApplication.update += OnUpdate;
            EditorApplication.playModeStateChanged += OnPlayModeStateChanged;
            AssemblyReloadEvents.beforeAssemblyReload += HandleBeforeAssemblyReload;
            subscribed = true;
        }

        internal static void HandleBeforeAssemblyReload()
        {
            AbortActive("interrupted_by_reload", "Domain Reload 打断手势");
        }

        private static void OnPlayModeStateChanged(PlayModeStateChange change)
        {
            if (change == PlayModeStateChange.ExitingPlayMode ||
                change == PlayModeStateChange.EnteredEditMode)
            {
                AbortActive("cancelled", "Play Mode 已退出，手势已取消");
            }
        }

        private static void OnUpdate()
        {
            if (active == null)
            {
                Unsubscribe();
                return;
            }

            JobRecord record = JobManager.GetJob(active.Handle.JobId);
            if (record != null && record.Status != JobStatus.Running)
            {
                TryCancel(active);
                active = null;
                Unsubscribe();
                return;
            }

            if (!EditorApplication.isPlaying)
            {
                AbortActive("cancelled", "Play Mode 已退出，手势已取消");
                return;
            }

            bool done;
            try
            {
                done = active.Backend.Tick(active.Session);
            }
            catch (Exception ex)
            {
                TryCancel(active);
                active.Handle.Fail("internal_error", ex.Message, BuildFailureResult(active.Session));
                active = null;
                Unsubscribe();
                return;
            }

            if (!done)
            {
                return;
            }

            CompleteActive();
        }

        private static void CompleteActive()
        {
            if (active == null)
            {
                return;
            }

            InteractionGestureSession session = active.Session;
            JobHandle handle = active.Handle;
            active = null;
            Unsubscribe();

            if (session.Result != null && session.Result.Ok)
            {
                handle.Succeed(BuildSuccessResult(session));
                return;
            }

            handle.Fail(
                session.Result?.ErrorCode ?? "internal_error",
                session.Result?.ErrorMessage ?? "手势失败",
                BuildFailureResult(session));
        }

        private static void AbortActive(string code, string message)
        {
            if (active == null)
            {
                return;
            }

            TryCancel(active);

            JobRecord record = JobManager.GetJob(active.Handle.JobId);
            if (record != null && record.Status == JobStatus.Running)
            {
                active.Handle.Fail(code, message, BuildFailureResult(active.Session));
            }

            active = null;
            Unsubscribe();
        }

        private static void TryCancel(ActiveGesture gesture)
        {
            try
            {
                gesture?.Backend?.Cancel(gesture.Session);
            }
            catch
            {
                // 游戏事件处理器异常不能阻断 single-flight 与订阅状态清理。
            }
        }

        private static void Unsubscribe()
        {
            if (!subscribed)
            {
                return;
            }

            EditorApplication.update -= OnUpdate;
            EditorApplication.playModeStateChanged -= OnPlayModeStateChanged;
            AssemblyReloadEvents.beforeAssemblyReload -= HandleBeforeAssemblyReload;
            subscribed = false;
        }

        private static object MapCompletedSession(InteractionGestureSession session)
        {
            InteractionOperationResult result = session.Result
                ?? InteractionOperationResult.Fail("internal_error", "手势未能启动");
            if (result.ErrorCode == "occluded" && result.RaycastHit != null)
            {
                JsonValue occludedJson = JsonValue.NewObject();
                occludedJson["ok"] = false;
                occludedJson["code"] = result.ErrorCode;
                occludedJson["message"] = result.ErrorMessage;
                occludedJson["blockedBy"] = NodePath.BuildPath(result.RaycastHit.transform);
                return occludedJson;
            }

            return BridgeResponse.Failure(result.ErrorCode, result.ErrorMessage);
        }

        private static Dictionary<string, object> BuildSuccessResult(InteractionGestureSession session)
        {
            List<object> events = new List<object>();
            foreach (string eventName in session.Events)
            {
                events.Add(eventName);
            }

            Dictionary<string, object> result = new Dictionary<string, object>
            {
                ["ok"] = true,
                ["kind"] = session.Kind,
                ["events"] = events,
                ["durationSeconds"] = session.DurationSeconds,
                ["start"] = PointDict(session.StartScreenPoint),
                ["end"] = PointDict(session.EndScreenPoint),
                ["forced"] = session.Result != null && session.Result.Forced
            };

            if (session.Result?.Clicked != null)
            {
                result["target"] = NodePath.BuildPath(session.Result.Clicked.transform);
            }

            if (session.Result?.RaycastHit != null)
            {
                result["raycastHit"] = NodePath.BuildPath(session.Result.RaycastHit.transform);
            }

            return result;
        }

        private static Dictionary<string, object> BuildFailureResult(InteractionGestureSession session)
        {
            if (session == null)
            {
                return null;
            }

            List<object> events = new List<object>();
            foreach (string eventName in session.Events)
            {
                events.Add(eventName);
            }

            Dictionary<string, object> result = new Dictionary<string, object>
            {
                ["ok"] = false,
                ["kind"] = session.Kind,
                ["code"] = session.Result?.ErrorCode,
                ["message"] = session.Result?.ErrorMessage,
                ["events"] = events,
                ["durationSeconds"] = session.DurationSeconds,
                ["start"] = PointDict(session.StartScreenPoint),
                ["end"] = PointDict(session.EndScreenPoint)
            };

            if (session.Result?.RaycastHit != null)
            {
                result["blockedBy"] = NodePath.BuildPath(session.Result.RaycastHit.transform);
            }

            return result;
        }

        private static Dictionary<string, object> PointDict(Vector2 point)
        {
            return new Dictionary<string, object>
            {
                ["x"] = point.x,
                ["y"] = point.y
            };
        }

        private static bool TryValidatePlayMode(out BridgeResponse rejection)
        {
            string editorState = EditorStateProvider.DeriveState(
                EditorApplication.isCompiling,
                EditorApplication.isUpdating,
                EditorApplication.isPlaying,
                EditorApplication.isPaused,
                EditorApplication.isPlayingOrWillChangePlaymode);

            return InteractionController.ValidatePlayModeState(editorState, out rejection);
        }

        private static bool IsFinite(double value)
        {
            return !double.IsNaN(value) && !double.IsInfinity(value);
        }

        private static bool IsFiniteFloat(double value)
        {
            return IsFinite(value) && value >= -float.MaxValue && value <= float.MaxValue;
        }

        /// <summary>测试钩子：重置 single-flight 状态。</summary>
        internal static void ResetForTests()
        {
            if (active != null)
            {
                TryCancel(active);
                active = null;
            }

            Unsubscribe();
        }
    }
}
