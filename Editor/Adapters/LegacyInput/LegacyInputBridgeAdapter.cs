using Mk.UnityAgentBridge.Editor.Contracts;

namespace Mk.UnityAgentBridge.Editor.Adapters.LegacyInput
{
    /// <summary>
    /// Legacy Input Manager Adapter：注册 Priority=100 的指针输入后端。
    /// 构造与 RegisterServices 禁止订阅全局事件。
    /// </summary>
    [BridgeAdapter]
    public sealed class LegacyInputBridgeAdapter : IBridgeAdapter
    {
        public int Priority => 100;

        public void RegisterServices(IBridgeServiceRegistry services)
        {
            LegacyPointerBackend backend = new LegacyPointerBackend();
            services.Add<IPointerInputBackend>(backend, backend.Priority);
        }
    }
}
