using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Interaction
{
    /// <summary>
    /// UGUI 点击 / 文本输入 / 受限设值。三个端点共用前置条件：必须 playing（paused 也拒绝——
    /// 事件能派发但游戏逻辑不推进，结果有误导性）；节点定位复用 Hierarchy 的 path/instanceId 解析。
    /// </summary>
    internal static class InteractionController
    {
        public static void RegisterRoutes()
        {
            CapabilityRegistry.Declare("interaction");
            RouteTable.Register("POST", "interaction/click", Click);
            RouteTable.Register("POST", "interaction/input", Input);
            RouteTable.Register("POST", "interaction/set-value", SetValue);
        }

        internal static object Click(BridgeRequestContext ctx)
        {
            JsonValue body = ctx.Body;
            if (body == null || !body.TryGetString("path", out string path))
            {
                return BridgeResponse.Failure("invalid_argument", "body 必须包含字符串字段 path");
            }

            bool force = body.GetBoolean("force", false);
            string scene = body.TryGetString("scene", out string sceneValue) ? sceneValue : null;

            if (!TryValidatePlayMode(out BridgeResponse gate))
            {
                return gate;
            }

            NodePath.ResolveResult resolved = NodePath.Resolve(path, scene);
            if (!resolved.Ok)
            {
                return BridgeResponse.Failure(resolved.ErrorCode, resolved.ErrorMessage);
            }

            PointerSimulator.ClickResult result = PointerSimulator.SimulateClick(resolved.Node.gameObject, force);
            if (!result.Ok)
            {
                BridgeResponse failure = BridgeResponse.Failure(result.ErrorCode, result.ErrorMessage);
                if (result.ErrorCode == "occluded" && result.RaycastHit != null)
                {
                    // BridgeResponse 是 JsonUtility DTO，塞不进额外字段；occluded 用 JsonValue
                    // 信封重新包一层，携带 blockedBy 供 agent 直接读取，不用去解析 message 文本。
                    JsonValue occludedJson = JsonValue.NewObject();
                    occludedJson["ok"] = false;
                    occludedJson["code"] = result.ErrorCode;
                    occludedJson["message"] = result.ErrorMessage;
                    occludedJson["blockedBy"] = NodePath.BuildPath(result.RaycastHit.transform);
                    return occludedJson;
                }

                return failure;
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["clicked"] = NodePath.BuildPath(result.Clicked.transform);
            response["raycastHit"] = result.RaycastHit == null ? JsonValue.Null : JsonValue.FromString(NodePath.BuildPath(result.RaycastHit.transform));
            response["forced"] = result.Forced;
            JsonValue eventsArray = JsonValue.NewArray();
            foreach (string eventName in result.Events)
            {
                eventsArray.Add(eventName);
            }

            response["events"] = eventsArray;
            return response;
        }

        internal static object Input(BridgeRequestContext ctx)
        {
            JsonValue body = ctx.Body;
            if (body == null || !body.TryGetString("path", out string path))
            {
                return BridgeResponse.Failure("invalid_argument", "body 必须包含字符串字段 path");
            }

            string text = body.TryGetString("text", out string textValue) ? textValue : string.Empty;
            bool submit = body.GetBoolean("submit", false);
            string scene = body.TryGetString("scene", out string sceneValue) ? sceneValue : null;

            if (!TryValidatePlayMode(out BridgeResponse gate))
            {
                return gate;
            }

            NodePath.ResolveResult resolved = NodePath.Resolve(path, scene);
            if (!resolved.Ok)
            {
                return BridgeResponse.Failure(resolved.ErrorCode, resolved.ErrorMessage);
            }

            InputSimulator.OperationResult result = InputSimulator.SetText(resolved.Node.gameObject, text, submit);
            if (!result.Ok)
            {
                return BridgeResponse.Failure(result.ErrorCode, result.ErrorMessage);
            }

            return BridgeResponse.Success("ok", "input applied");
        }

        internal static object SetValue(BridgeRequestContext ctx)
        {
            JsonValue body = ctx.Body;
            if (body == null || !body.TryGetString("path", out string path))
            {
                return BridgeResponse.Failure("invalid_argument", "body 必须包含字符串字段 path");
            }

            string component = body.TryGetString("component", out string componentValue) ? componentValue : null;
            string scene = body.TryGetString("scene", out string sceneValue) ? sceneValue : null;
            JsonValue value = body.TryGet("value", out JsonValue valueItem) ? valueItem : null;

            if (!TryValidatePlayMode(out BridgeResponse gate))
            {
                return gate;
            }

            NodePath.ResolveResult resolved = NodePath.Resolve(path, scene);
            if (!resolved.Ok)
            {
                return BridgeResponse.Failure(resolved.ErrorCode, resolved.ErrorMessage);
            }

            InputSimulator.OperationResult result = InputSimulator.SetValue(resolved.Node.gameObject, component, value);
            if (!result.Ok)
            {
                return BridgeResponse.Failure(result.ErrorCode, result.ErrorMessage);
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["component"] = result.ComponentType;
            return response;
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
            string editorState = EditorStateProvider.DeriveState(
                EditorApplication.isCompiling,
                EditorApplication.isUpdating,
                EditorApplication.isPlaying,
                EditorApplication.isPaused,
                EditorApplication.isPlayingOrWillChangePlaymode);

            return ValidatePlayModeState(editorState, out rejection);
        }
    }
}
