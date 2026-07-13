using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Json;

namespace Mk.UnityAgentBridge.Editor.Routing
{
    /// <summary>
    /// 封装单次请求的 query 参数、body（惰性解析）与路径参数，Controller 不再直接接触
    /// HttpListenerRequest。既有端点仍可通过 <see cref="RawBody"/> 走 JsonUtility 解析
    /// （保持不迁移）；新增端点使用 <see cref="Body"/>（自写 JsonParser 解析出的 JsonValue）。
    /// </summary>
    public sealed class BridgeRequestContext : IBridgeRequestContext
    {
        private readonly Dictionary<string, string> queryParams;
        private readonly Lazy<JsonValue> lazyBody;

        public HttpListenerRequest Request { get; }
        public string PathParam { get; }
        public string RawBody { get; }

        public BridgeRequestContext(HttpListenerRequest request, string pathParam)
        {
            Request = request;
            PathParam = pathParam;
            RawBody = ReadRawBody(request);
            queryParams = ParseQuery(request.Url?.Query);
            lazyBody = new Lazy<JsonValue>(() => SafeParseBody(RawBody));
        }

        /// <summary>
        /// 测试专用构造函数：绕过 HttpListenerRequest（EditMode 测试中无法构造真实实例），
        /// 直接注入 pathParam / body / query。生产代码不应使用。
        /// </summary>
        internal BridgeRequestContext(string pathParam, string rawBody = "", IReadOnlyDictionary<string, string> query = null)
        {
            Request = null;
            PathParam = pathParam;
            RawBody = rawBody ?? string.Empty;
            queryParams = new Dictionary<string, string>(StringComparer.Ordinal);
            if (query != null)
            {
                foreach (KeyValuePair<string, string> pair in query)
                {
                    queryParams[pair.Key.ToLowerInvariant()] = pair.Value;
                }
            }

            lazyBody = new Lazy<JsonValue>(() => SafeParseBody(RawBody));
        }

        internal static BridgeRequestContext ForTests(
            string pathParam = null,
            string rawBody = "",
            IReadOnlyDictionary<string, string> query = null)
        {
            return new BridgeRequestContext(pathParam, rawBody, query);
        }

        /// <summary>解析失败或空 body 时返回 null；调用方需自行判空后返回 invalid_request。</summary>
        public JsonValue Body => lazyBody.Value;

        public bool HasQuery(string key) => queryParams.ContainsKey(key.ToLowerInvariant());

        public string GetQuery(string key, string defaultValue = null)
        {
            return queryParams.TryGetValue(key.ToLowerInvariant(), out string value) ? value : defaultValue;
        }

        public int GetQueryInt(string key, int defaultValue)
        {
            string raw = GetQuery(key);
            return raw != null && int.TryParse(raw, out int value) ? value : defaultValue;
        }

        public bool GetQueryBool(string key, bool defaultValue)
        {
            string raw = GetQuery(key);
            if (raw == null)
            {
                return defaultValue;
            }

            return raw switch
            {
                "true" or "1" or "yes" => true,
                "false" or "0" or "no" => false,
                _ => defaultValue
            };
        }

        public IReadOnlyDictionary<string, string> QueryParams => queryParams;

        private static string ReadRawBody(HttpListenerRequest request)
        {
            if (!request.HasEntityBody)
            {
                return string.Empty;
            }

            using StreamReader reader = new StreamReader(request.InputStream, request.ContentEncoding);
            return reader.ReadToEnd();
        }

        private static JsonValue SafeParseBody(string raw)
        {
            if (string.IsNullOrWhiteSpace(raw))
            {
                return null;
            }

            try
            {
                return JsonParser.Parse(raw);
            }
            catch (JsonParseException)
            {
                return null;
            }
        }

        internal static Dictionary<string, string> ParseQuery(string query)
        {
            Dictionary<string, string> result = new Dictionary<string, string>(StringComparer.Ordinal);
            if (string.IsNullOrEmpty(query))
            {
                return result;
            }

            string trimmed = query.TrimStart('?');
            if (trimmed.Length == 0)
            {
                return result;
            }

            foreach (string pair in trimmed.Split('&'))
            {
                if (pair.Length == 0)
                {
                    continue;
                }

                int separatorIndex = pair.IndexOf('=');
                string rawKey = separatorIndex < 0 ? pair : pair.Substring(0, separatorIndex);
                string rawValue = separatorIndex < 0 ? string.Empty : pair.Substring(separatorIndex + 1);
                string key = WebUtility.UrlDecode(rawKey).ToLowerInvariant();
                string value = WebUtility.UrlDecode(rawValue);
                result[key] = value;
            }

            return result;
        }
    }
}
