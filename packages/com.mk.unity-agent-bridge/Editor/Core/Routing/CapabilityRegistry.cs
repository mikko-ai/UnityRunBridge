using System.Collections.Generic;

namespace Mk.UnityAgentBridge.Editor.Routing
{
    /// <summary>
    /// 兼容门面：Phase 2 起真正的 capability 集合是 <see cref="BridgeRuntime"/> 持有的实例
    /// <see cref="InstanceCapabilityRegistry"/>，本静态类只把读写转发到 active runtime，
    /// 保留既有 Controller 测试 / 契约测试直接调用 <c>CapabilityRegistry.Declare/All</c> 的能力。
    /// </summary>
    public static class CapabilityRegistry
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
            Runtime.Capabilities.Clear();
        }

        public static void Declare(string capability)
        {
            Runtime.Capabilities.Declare(capability);
        }

        public static IReadOnlyList<string> All()
        {
            return Runtime.Capabilities.All();
        }
    }
}
