using UnityEditor;
using Mk.UnityAgentBridge.Editor.Routing;

namespace Mk.UnityAgentBridge.Editor
{
    /// <summary>
    /// 承载不属于任何专职 Controller 的基础端点（status / refresh）。
    /// </summary>
    internal static class CoreController
    {
        public static void RegisterRoutes()
        {
            RouteTable.Register("GET", "status", ctx => EditorStateProvider.GetStatus());
            RouteTable.Register("POST", "refresh", ctx =>
            {
                AssetDatabase.Refresh();
                return BridgeResponse.Success("accepted", "asset refresh triggered");
            });
        }
    }
}
