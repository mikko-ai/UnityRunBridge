using Mk.UnityAgentBridge.Editor.Json;

namespace Mk.UnityAgentBridge.Editor.Routing
{
    internal static class CapabilitiesController
    {
        public static void RegisterRoutes()
        {
            RouteTable.Register("GET", "capabilities", ctx => BuildResponse());
        }

        internal static JsonValue BuildResponse()
        {
            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["bridgeVersion"] = BridgeConfig.Version;

            JsonValue capabilities = JsonValue.NewArray();
            foreach (string capability in CapabilityRegistry.All())
            {
                capabilities.Add(capability);
            }

            response["capabilities"] = capabilities;

            JsonValue routes = JsonValue.NewArray();
            foreach ((string method, string path) in RouteTable.ListRoutes())
            {
                JsonValue route = JsonValue.NewObject();
                route["method"] = method;
                route["path"] = path;
                routes.Add(route);
            }

            response["routes"] = routes;
            return response;
        }
    }
}
