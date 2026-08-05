using System;
using System.Collections.Generic;

namespace Mk.UnityAgentBridge.Editor
{
    /// <summary>
    /// 全局错误码 → HTTP 状态码映射表。所有 Phase 新增的失败 code 必须在此登记；
    /// 缺映射默认 500（安全默认：宁可暴露成「未分类的服务器错误」，也不能让忘记登记的
    /// 错误码被误判成 200）。<see cref="ResolveHttpStatus"/> 只应在 response.ok == false 时调用；
    /// ok == true 的响应恒为 200，不查表。
    /// </summary>
    public static class BridgeErrorCodes
    {
        public const int DefaultFailureStatus = 500;

        private static readonly Dictionary<string, int> CodeToStatus = new Dictionary<string, int>(StringComparer.Ordinal)
        {
            // 既有（0.1 之前）
            ["unauthorized"] = 401,
            ["not_found"] = 404,
            ["busy"] = 409,
            ["compilation_failed"] = 409,
            ["invalid_request"] = 422,
            ["internal_error"] = 500,

            // Phase 0：job / artifacts
            ["job_not_found"] = 404,
            ["too_many_jobs"] = 409,

            // Phase 1：hierarchy / capture
            ["invalid_argument"] = 422,
            ["node_not_found"] = 404,
            ["ambiguous_path"] = 422,
            ["ambiguous_component"] = 422,
            ["unknown_component"] = 422,
            ["stale_cursor"] = 409,
            ["capture_disabled"] = 403,
            ["agent_capture_denied"] = 403,
            ["capture_requires_play_mode"] = 409,
            ["capture_unavailable"] = 409,
            ["capture_quota_exceeded"] = 429,
            ["capture_failed"] = 500,

            // Phase 2：interaction / gameplay / recording
            ["not_in_play_mode"] = 409,
            ["no_event_system"] = 422,
            ["node_inactive"] = 409,
            ["occluded"] = 409,
            ["no_click_handler"] = 422,
            ["not_interactable"] = 409,
            ["not_input_field"] = 422,
            ["unsupported_set_value"] = 422,
            ["gameplay_disabled"] = 403,
            ["command_not_found"] = 404,
            ["invoke_failed"] = 500,
            ["unsupported_signature"] = 422,
            ["already_recording"] = 409,
            ["no_input_backend"] = 422,
            ["interaction_busy"] = 409,
            ["bridge_capability_missing"] = 422,
            ["cancelled"] = 409,

            // Phase 4：profiling / build / health
            ["already_profiling"] = 409,
            ["metric_not_available"] = 422,
            ["already_scanning"] = 409,
        };

        public static int ResolveHttpStatus(string code)
        {
            if (string.IsNullOrEmpty(code))
            {
                return DefaultFailureStatus;
            }

            return CodeToStatus.TryGetValue(code, out int status) ? status : DefaultFailureStatus;
        }

        /// <summary>供 EditMode 测试断言表内容完整性，不用于运行时逻辑。</summary>
        internal static bool IsRegistered(string code) => CodeToStatus.ContainsKey(code);
    }
}
