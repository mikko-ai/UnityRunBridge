using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;

namespace Mk.UnityAgentBridge.Editor.Gameplay
{
    /// <summary>
    /// 零侵入 gameplay command bridge：GET /gameplay/commands 列出可调用命令菜单，
    /// POST /gameplay/invoke 在主线程执行。两条发现通道（duck-typed attribute + 白名单直调）
    /// 均只在 Play Mode 下可用，且受 config.json 的 gameplay.enabled 总开关控制（默认 false）。
    /// 实际的命令解析交给 <see cref="GameplayCommandRegistry"/>，参数转换与调用交给
    /// <see cref="GameplayInvoker"/>，本类只负责门禁、JSON 编解码与审计落盘。
    /// </summary>
    internal static class GameplayController
    {
        public static void RegisterRoutes()
        {
            CapabilityRegistry.Declare("gameplay");
            RouteTable.Register("GET", "gameplay/commands", ListCommands);
            RouteTable.Register("POST", "gameplay/invoke", Invoke);
        }

        internal static object ListCommands(BridgeRequestContext ctx)
        {
            BridgeProjectConfig.GameplaySettings settings = BridgeProjectConfig.Load().Gameplay;
            if (!TryValidateGate(settings, out BridgeResponse gate))
            {
                return gate;
            }

            List<GameplayCommandRegistry.CommandInfo> commands =
                new List<GameplayCommandRegistry.CommandInfo>(GameplayCommandRegistry.DiscoverAttributeCommands());

            foreach (string fullyQualifiedName in settings.Whitelist)
            {
                if (GameplayCommandRegistry.TryResolveWhitelistCommand(
                    fullyQualifiedName, settings.Whitelist, out GameplayCommandRegistry.CommandInfo whitelisted,
                    out string _, out string _))
                {
                    commands.Add(whitelisted);
                }
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            JsonValue array = JsonValue.NewArray();
            foreach (GameplayCommandRegistry.CommandInfo command in commands)
            {
                array.Add(SerializeCommand(command));
            }

            response["commands"] = array;
            return response;
        }

        internal static object Invoke(BridgeRequestContext ctx)
        {
            JsonValue body = ctx.Body;
            if (body == null || !body.TryGetString("command", out string commandName) || string.IsNullOrWhiteSpace(commandName))
            {
                return BridgeResponse.Failure("invalid_argument", "body 必须包含字符串字段 command");
            }

            JsonValue args = body.TryGetObject("args", out JsonValue argsValue) ? argsValue : JsonValue.NewObject();
            string reason = body.TryGetString("reason", out string reasonValue) ? reasonValue : "agent";

            BridgeProjectConfig.GameplaySettings settings = BridgeProjectConfig.Load().Gameplay;
            if (!TryValidateGate(settings, out BridgeResponse gate))
            {
                return gate;
            }

            if (!GameplayCommandRegistry.Resolve(commandName, settings.Whitelist, out GameplayCommandRegistry.CommandInfo command,
                out string resolveErrorCode, out string resolveErrorMessage))
            {
                return BridgeResponse.Failure(resolveErrorCode, resolveErrorMessage);
            }

            if (!command.Invocable)
            {
                return BridgeResponse.Failure(
                    "unsupported_signature",
                    $"命令 {commandName} 的签名不受支持：{command.InvocableReason}");
            }

            if (!GameplayInvoker.TryBuildArguments(command, args, out object[] callArgs, out string argErrorCode, out string argErrorMessage))
            {
                return BridgeResponse.Failure(argErrorCode, argErrorMessage);
            }

            GameplayInvoker.InvokeResult result = GameplayInvoker.Invoke(command, callArgs);
            GameplayAuditLog.Append(commandName, args, result.Ok ? result.ResultJson : JsonValue.Null, result.DurationMs, reason);

            if (!result.Ok)
            {
                return BridgeResponse.Failure(result.ErrorCode, result.ErrorMessage);
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["result"] = result.ResultJson;
            response["durationMs"] = result.DurationMs;
            return response;
        }

        private static JsonValue SerializeCommand(GameplayCommandRegistry.CommandInfo command)
        {
            JsonValue json = JsonValue.NewObject();
            json["name"] = command.Name;
            json["assembly"] = command.AssemblyName;

            JsonValue parameters = JsonValue.NewArray();
            foreach (GameplayCommandRegistry.ParamInfo parameter in command.Parameters)
            {
                JsonValue parameterJson = JsonValue.NewObject();
                parameterJson["name"] = parameter.Name;
                parameterJson["type"] = parameter.Type;
                parameters.Add(parameterJson);
            }

            json["parameters"] = parameters;
            json["returnType"] = command.ReturnType;
            json["source"] = command.Source;
            json["invocable"] = command.Invocable;
            if (!command.Invocable)
            {
                json["invocableReason"] = command.InvocableReason;
            }

            return json;
        }

        /// <summary>抽成纯函数（接收 settings + 当前 editorState）便于 EditMode 测试覆盖各拒绝分支。</summary>
        internal static bool ValidateGateState(
            BridgeProjectConfig.GameplaySettings settings, string editorState, out BridgeResponse rejection)
        {
            if (!settings.Enabled)
            {
                rejection = BridgeResponse.Failure(
                    "gameplay_disabled",
                    "gameplay command bridge 已关闭，请在 config.json 的 gameplay.enabled 中开启");
                return false;
            }

            if (editorState != "playing")
            {
                rejection = BridgeResponse.Failure(
                    "not_in_play_mode", $"该操作需要 Play Mode（当前 editorState={editorState}）");
                return false;
            }

            rejection = null;
            return true;
        }

        private static bool TryValidateGate(BridgeProjectConfig.GameplaySettings settings, out BridgeResponse rejection)
        {
            string editorState = EditorStateProvider.DeriveState(
                EditorApplication.isCompiling,
                EditorApplication.isUpdating,
                EditorApplication.isPlaying,
                EditorApplication.isPaused,
                EditorApplication.isPlayingOrWillChangePlaymode);

            return ValidateGateState(settings, editorState, out rejection);
        }
    }
}
