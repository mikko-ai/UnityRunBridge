using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;

namespace Mk.UnityAgentBridge.Editor.Routing
{
    public delegate object RouteHandler(BridgeRequestContext context);

    /// <summary>
    /// 兼容门面：Phase 2 起真正的路由表是 <see cref="BridgeRuntime"/> 持有的实例
    /// <see cref="InstanceRouteTable"/>，本静态类只把读写转发到 active runtime，
    /// 保留既有 Controller 测试 / 契约测试直接调用 <c>RouteTable.Register/Resolve/ListRoutes</c> 的能力。
    ///
    /// 生产装配（Host）走实例 API（<see cref="IRouteRegistrar"/>），候选发布前不经过本门面，
    /// 因此本门面不会污染尚未发布的候选 runtime。Host 尚未 publish 时，门面惰性发布一份空 runtime
    /// 兜底，避免 NRE（正常流程中 Host 的 InitializeOnLoad 会先发布装配完成的 runtime）。
    /// </summary>
    public static class RouteTable
    {
        private static BridgeRuntime Runtime
        {
            get
            {
                BridgeRuntime active = BridgeRuntime.Active;
                if (active == null)
                {
                    active = new BridgeRuntime();
                    BridgeRuntime.Publish(active);
                }

                return active;
            }
        }

        public static void Reset()
        {
            Runtime.Routes.Clear();
        }

        public static void Register(string method, string pathPattern, RouteHandler handler)
        {
            RouteHandler captured = handler;
            Runtime.Routes.Map(method, pathPattern, context => captured((BridgeRequestContext)context));
        }

        public static bool Unregister(string method, string pathPattern)
        {
            return Runtime.Routes.Unregister(method, pathPattern);
        }

        public static RouteHandler Resolve(string method, string path, out string pathParam)
        {
            BridgeRouteHandler handler = Runtime.Routes.Resolve(method, path, out pathParam);
            if (handler == null)
            {
                return null;
            }

            return context => handler(context);
        }

        public static IReadOnlyList<(string Method, string Path)> ListRoutes()
        {
            return Runtime.Routes.ListRoutes();
        }
    }
}
