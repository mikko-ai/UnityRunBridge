using System;
using System.Diagnostics;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Interaction
{
    /// <summary>
    /// interaction/* 路由编排：Play Mode 门禁、路径解析与结果映射。
    /// Phase 3：经显式注入或 active runtime 的服务契约调用 Adapter 实现。
    /// </summary>
    internal static class InteractionController
    {
        private static Func<string> playModeStateProvider = DeriveEditorState;

        internal static object Click(BridgeRequestContext ctx, IBridgeServiceResolver services = null)
        {
            Stopwatch stopwatch = Stopwatch.StartNew();
            JsonValue body = ctx.Body;
            JsonValue request = InteractionAuditLog.BuildRequestSummary("click", body);
            string scene = body != null && body.TryGetString("scene", out string sceneValue)
                ? sceneValue
                : null;
            if (body == null || !body.TryGetString("path", out string path) ||
                string.IsNullOrWhiteSpace(path))
            {
                return AuditAndReturn(
                    "click", request, scene,
                    BridgeResponse.Failure("invalid_argument", "body 必须包含字符串字段 path"), stopwatch);
            }

            bool force = body.GetBoolean("force", false);

            if (!TryValidatePlayMode(out BridgeResponse gate))
            {
                return AuditAndReturn("click", request, scene, gate, stopwatch);
            }

            NodePath.ResolveResult resolved = NodePath.Resolve(path, scene);
            if (!resolved.Ok)
            {
                return AuditAndReturn(
                    "click", request, scene,
                    BridgeResponse.Failure(resolved.ErrorCode, resolved.ErrorMessage), stopwatch);
            }

            services = BridgeServices.Current(services);
            PointerSimulator.ClickResult result = PointerSimulator.SimulateClick(
                resolved.Node.gameObject, force, services);
            if (!result.Ok)
            {
                BridgeResponse failure = BridgeResponse.Failure(result.ErrorCode, result.ErrorMessage);
                if (result.ErrorCode == "occluded" && result.RaycastHit != null)
                {
                    JsonValue occludedJson = JsonValue.NewObject();
                    occludedJson["ok"] = false;
                    occludedJson["code"] = result.ErrorCode;
                    occludedJson["message"] = result.ErrorMessage;
                    occludedJson["blockedBy"] = NodePath.BuildPath(result.RaycastHit.transform);
                    return AuditAndReturn("click", request, scene, occludedJson, stopwatch);
                }

                return AuditAndReturn("click", request, scene, failure, stopwatch);
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["clicked"] = NodePath.BuildPath(result.Clicked.transform);
            response["raycastHit"] = result.RaycastHit == null
                ? JsonValue.Null
                : JsonValue.FromString(NodePath.BuildPath(result.RaycastHit.transform));
            response["forced"] = result.Forced;
            JsonValue eventsArray = JsonValue.NewArray();
            foreach (string eventName in result.Events)
            {
                eventsArray.Add(eventName);
            }

            response["events"] = eventsArray;
            return AuditAndReturn("click", request, scene, response, stopwatch);
        }

        internal static object Input(BridgeRequestContext ctx, IBridgeServiceResolver services = null)
        {
            Stopwatch stopwatch = Stopwatch.StartNew();
            JsonValue body = ctx.Body;
            JsonValue request = InteractionAuditLog.BuildRequestSummary("input", body);
            string scene = body != null && body.TryGetString("scene", out string sceneValue)
                ? sceneValue
                : null;
            if (body == null || !body.TryGetString("path", out string path) ||
                string.IsNullOrWhiteSpace(path))
            {
                return AuditAndReturn(
                    "input", request, scene,
                    BridgeResponse.Failure("invalid_argument", "body 必须包含字符串字段 path"), stopwatch);
            }

            string text = body.TryGetString("text", out string textValue) ? textValue : string.Empty;
            bool submit = body.GetBoolean("submit", false);

            if (!TryValidatePlayMode(out BridgeResponse gate))
            {
                return AuditAndReturn("input", request, scene, gate, stopwatch);
            }

            NodePath.ResolveResult resolved = NodePath.Resolve(path, scene);
            if (!resolved.Ok)
            {
                return AuditAndReturn(
                    "input", request, scene,
                    BridgeResponse.Failure(resolved.ErrorCode, resolved.ErrorMessage), stopwatch);
            }

            services = BridgeServices.Current(services);
            InputSimulator.OperationResult result = InputSimulator.SetText(
                resolved.Node.gameObject, text, submit, services);
            if (!result.Ok)
            {
                return AuditAndReturn(
                    "input", request, scene,
                    BridgeResponse.Failure(result.ErrorCode, result.ErrorMessage), stopwatch);
            }

            return AuditAndReturn(
                "input", request, scene, BridgeResponse.Success("ok", "input applied"), stopwatch);
        }

        internal static object SetValue(BridgeRequestContext ctx, IBridgeServiceResolver services = null)
        {
            Stopwatch stopwatch = Stopwatch.StartNew();
            JsonValue body = ctx.Body;
            JsonValue request = InteractionAuditLog.BuildRequestSummary("set-value", body);
            string scene = body != null && body.TryGetString("scene", out string sceneValue)
                ? sceneValue
                : null;
            if (body == null || !body.TryGetString("path", out string path) ||
                string.IsNullOrWhiteSpace(path))
            {
                return AuditAndReturn(
                    "set-value", request, scene,
                    BridgeResponse.Failure("invalid_argument", "body 必须包含字符串字段 path"), stopwatch);
            }

            string component = body.TryGetString("component", out string componentValue) ? componentValue : null;
            JsonValue value = body.TryGet("value", out JsonValue valueItem) ? valueItem : null;

            if (!TryValidatePlayMode(out BridgeResponse gate))
            {
                return AuditAndReturn("set-value", request, scene, gate, stopwatch);
            }

            NodePath.ResolveResult resolved = NodePath.Resolve(path, scene);
            if (!resolved.Ok)
            {
                return AuditAndReturn(
                    "set-value", request, scene,
                    BridgeResponse.Failure(resolved.ErrorCode, resolved.ErrorMessage), stopwatch);
            }

            services = BridgeServices.Current(services);
            InputSimulator.OperationResult result = InputSimulator.SetValue(
                resolved.Node.gameObject, component, value, services);
            if (!result.Ok)
            {
                return AuditAndReturn(
                    "set-value", request, scene,
                    BridgeResponse.Failure(result.ErrorCode, result.ErrorMessage), stopwatch);
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["component"] = result.ComponentType;
            return AuditAndReturn("set-value", request, scene, response, stopwatch);
        }

        /// <summary>抽成纯函数（接收当前 editorState）便于 EditMode 测试覆盖三种拒绝分支，不依赖真实 Play Mode。</summary>
        internal static bool ValidatePlayModeState(string editorState, out BridgeResponse rejection)
        {
            if (editorState == "playing")
            {
                rejection = null;
                return true;
            }

            rejection = BridgeResponse.Failure("not_in_play_mode", $"该操作需要 Play Mode（当前 editorState={editorState}）");
            return false;
        }

        private static bool TryValidatePlayMode(out BridgeResponse rejection)
        {
            return ValidatePlayModeState(playModeStateProvider(), out rejection);
        }

        private static string DeriveEditorState()
        {
            return EditorStateProvider.DeriveState(
                EditorApplication.isCompiling,
                EditorApplication.isUpdating,
                EditorApplication.isPlaying,
                EditorApplication.isPaused,
                EditorApplication.isPlayingOrWillChangePlaymode);
        }

        private static object AuditAndReturn(
            string action,
            JsonValue request,
            string scene,
            object response,
            Stopwatch stopwatch)
        {
            InteractionAuditLog.AppendFromResponse(
                action, request, scene, response, stopwatch.ElapsedMilliseconds);
            return response;
        }

        internal static void SetPlayModeStateProviderForTests(Func<string> provider)
        {
            playModeStateProvider = provider ?? DeriveEditorState;
        }

        internal static void ResetForTests()
        {
            playModeStateProvider = DeriveEditorState;
        }
    }
}
