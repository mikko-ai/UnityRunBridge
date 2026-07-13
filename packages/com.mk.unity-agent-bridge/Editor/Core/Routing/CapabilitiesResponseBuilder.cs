using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Json;

namespace Mk.UnityAgentBridge.Editor.Routing
{
    /// <summary>
    /// GET /capabilities 响应构造：从给定的 capability 列表与路由列表拼装信封。
    /// 抽到 Core 作为唯一实现，供旧单体的 CapabilitiesController 与 Host 的 capabilities 端点共用，
    /// 保证两条读取路径（静态门面 vs Host 直接读 runtime）产出的 JSON 形状完全一致。
    /// </summary>
    public static class CapabilitiesResponseBuilder
    {
        public static JsonValue Build(IReadOnlyList<string> capabilities, IReadOnlyList<(string Method, string Path)> routes)
        {
            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["bridgeVersion"] = BridgeConfig.Version;

            JsonValue capabilitiesArray = JsonValue.NewArray();
            if (capabilities != null)
            {
                foreach (string capability in capabilities)
                {
                    capabilitiesArray.Add(capability);
                }
            }

            response["capabilities"] = capabilitiesArray;

            JsonValue routesArray = JsonValue.NewArray();
            if (routes != null)
            {
                foreach ((string method, string path) in routes)
                {
                    JsonValue route = JsonValue.NewObject();
                    route["method"] = method;
                    route["path"] = path;
                    routesArray.Add(route);
                }
            }

            response["routes"] = routesArray;
            return response;
        }
    }
}
