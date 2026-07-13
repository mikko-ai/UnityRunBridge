using System.Net;
using System.Text;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Host
{
    /// <summary>
    /// 响应载荷 → HTTP 状态码 + JSON 字节。状态码只在 ok==false 时查 <see cref="BridgeErrorCodes"/>，
    /// ok==true 恒 200；无法识别的载荷保守 200。序列化区分 BridgeResponse（JsonUtility）与其余（JsonWriter）。
    /// Phase 2 从旧单体 BridgeServer 拆出到 Host 独立文件。
    /// </summary>
    internal static class ResponseSerializer
    {
        public static int ResolveStatusCode(object payload)
        {
            // 纯映射已下沉到 Core（BridgeResponseStatus），此处仅转发，保持单一真值来源。
            return BridgeResponseStatus.ResolveStatusCode(payload);
        }

        public static void WriteJson(HttpListenerResponse response, int statusCode, object payload)
        {
            string json = payload is BridgeResponse bridgeResponse
                ? JsonUtility.ToJson(bridgeResponse)
                : JsonWriter.Serialize(payload);
            byte[] bytes = Encoding.UTF8.GetBytes(json);
            response.StatusCode = statusCode;
            response.ContentType = "application/json";
            response.ContentEncoding = Encoding.UTF8;
            response.ContentLength64 = bytes.Length;
            response.OutputStream.Write(bytes, 0, bytes.Length);
            response.OutputStream.Close();
        }
    }
}
