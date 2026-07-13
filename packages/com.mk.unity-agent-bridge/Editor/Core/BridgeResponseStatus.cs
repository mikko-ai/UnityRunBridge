using Mk.UnityAgentBridge.Editor.Json;

namespace Mk.UnityAgentBridge.Editor
{
    /// <summary>
    /// 响应载荷 → HTTP 状态码的纯映射（Phase 2 从旧单体 BridgeServer 下沉到 Core）：
    /// 只在 ok==false 时查 <see cref="BridgeErrorCodes"/>，ok==true 恒 200；无法识别的载荷保守返回 200。
    /// Host 的 <c>ResponseSerializer</c> 与既有测试都调用本 Core 实现，保持单一真值来源。
    /// </summary>
    public static class BridgeResponseStatus
    {
        public static int ResolveStatusCode(object payload)
        {
            if (!TryExtractEnvelope(payload, out bool ok, out string code))
            {
                return 200;
            }

            return ok ? 200 : BridgeErrorCodes.ResolveHttpStatus(code);
        }

        private static bool TryExtractEnvelope(object payload, out bool ok, out string code)
        {
            switch (payload)
            {
                case null:
                    ok = true;
                    code = null;
                    return false;
                case BridgeResponse bridgeResponse:
                    ok = bridgeResponse.ok;
                    code = bridgeResponse.code;
                    return true;
                case JsonValue jsonValue when jsonValue.IsObject:
                    ok = jsonValue.GetBoolean("ok", true);
                    code = jsonValue.GetString("code");
                    return true;
                default:
                    ok = true;
                    code = null;
                    return false;
            }
        }
    }
}
