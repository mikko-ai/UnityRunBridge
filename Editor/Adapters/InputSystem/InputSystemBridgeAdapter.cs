using Mk.UnityAgentBridge.Editor.Contracts;

namespace Mk.UnityAgentBridge.Editor.Adapters.InputSystem
{
    /// <summary>
    /// Input System Adapter：注册 Priority=200 的指针输入后端。
    /// 构造与 RegisterServices 禁止订阅全局事件。
    /// </summary>
    [BridgeAdapter]
    public sealed class InputSystemBridgeAdapter : IBridgeAdapter
    {
        public int Priority => 200;

        public void RegisterServices(IBridgeServiceRegistry services)
        {
            InputSystemPointerBackend backend = new InputSystemPointerBackend();
            services.Add<IPointerInputBackend>(backend, backend.Priority);
        }
    }
}
