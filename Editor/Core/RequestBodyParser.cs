using System;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor
{
    /// <summary>
    /// 请求体解析（Phase 1 从 BridgeServer.ParseJsonOrNull 抽出到 Core）：
    /// JsonUtility.FromJson 对非法 JSON 会抛异常，这里统一转成 null，由调用方返回
    /// invalid_request(422) 而不是落入外层的 internal_error(500)。Feature/Controller 统一
    /// 调用本类；BridgeServer.ParseJsonOrNull 委托到此以保持既有测试兼容。
    /// </summary>
    public static class RequestBodyParser
    {
        public static T ParseJsonOrNull<T>(string json) where T : class
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                return null;
            }

            try
            {
                return JsonUtility.FromJson<T>(json);
            }
            catch (Exception)
            {
                return null;
            }
        }
    }
}
