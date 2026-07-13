using Mk.UnityAgentBridge.Editor.Json;

namespace Mk.UnityAgentBridge.Editor.Routing
{
    /// <summary>
    /// GET /capabilities 的兼容入口：Phase 2 起路由由 Host 最后注册，实际响应由 Core 的
    /// <see cref="CapabilitiesResponseBuilder"/> 从 active runtime 快照拼装。本类保留 BuildResponse
    /// 供既有测试（读静态门面 → active runtime）直接调用，与 Host 端点读取同一份数据、形状一致。
    /// </summary>
    internal static class CapabilitiesController
    {
        internal static JsonValue BuildResponse()
        {
            return CapabilitiesResponseBuilder.Build(CapabilityRegistry.All(), RouteTable.ListRoutes());
        }
    }
}
