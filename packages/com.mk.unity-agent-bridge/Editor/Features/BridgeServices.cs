using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Routing;

namespace Mk.UnityAgentBridge.Editor
{
    /// <summary>
    /// 优先使用显式注入的 resolver，否则回退到 active runtime。
    /// Module 路由闭包应捕获候选 resolver；本辅助仅给尚未注入路径的调用兜底。
    /// </summary>
    internal static class BridgeServices
    {
        public static IBridgeServiceResolver Current(IBridgeServiceResolver injected = null)
        {
            if (injected != null)
            {
                return injected;
            }

            return BridgeRuntime.Active?.Services;
        }
    }
}
