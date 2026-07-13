using System.Net;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Routing;

namespace Mk.UnityAgentBridge.Editor.Host
{
    /// <summary>
    /// 请求管线：鉴权 → 路由解析 → handler 分发。只读 active runtime 的路由快照，不接触装配过程。
    /// Phase 2 从旧单体 BridgeServer 拆出到 Host 独立文件。
    /// </summary>
    internal static class BridgeRequestPipeline
    {
        public static object Route(HttpListenerRequest request)
        {
            if (!IsAuthorized(request))
            {
                return BridgeResponse.Failure("unauthorized", "missing or invalid X-Bridge-Token header");
            }

            string method = request.HttpMethod.ToUpperInvariant();
            string path = request.Url.AbsolutePath.Trim('/').ToLowerInvariant();

            BridgeRuntime active = BridgeRuntime.Active;
            if (active == null)
            {
                return BridgeResponse.Failure("internal_error", "bridge runtime not composed yet");
            }

            BridgeRouteHandler handler = active.Routes.Resolve(method, path, out string pathParam);
            if (handler == null)
            {
                return BridgeResponse.Failure("not_found", $"unsupported route: {method} /{path}");
            }

            BridgeRequestContext context = new BridgeRequestContext(request, pathParam);
            return handler(context);
        }

        private static bool IsAuthorized(HttpListenerRequest request)
        {
            string expectedToken = BridgeInfoFile.GetOrCreateToken();
            string providedToken = request.Headers["X-Bridge-Token"];
            return BridgeServer.IsTokenValid(providedToken, expectedToken);
        }
    }
}
