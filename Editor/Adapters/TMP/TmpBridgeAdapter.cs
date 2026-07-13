using Mk.UnityAgentBridge.Editor.Contracts;

namespace Mk.UnityAgentBridge.Editor.Adapters.TMP
{
    /// <summary>
    /// TMP Adapter：注册文本控件与节点增强。不声明新 capability。
    /// 构造与 RegisterServices 禁止订阅全局事件。
    /// </summary>
    [BridgeAdapter]
    public sealed class TmpBridgeAdapter : IBridgeAdapter
    {
        public int Priority => 90;

        public void RegisterServices(IBridgeServiceRegistry services)
        {
            TmpNodeEnricher enricher = new TmpNodeEnricher();
            TmpTextControlAdapter text = new TmpTextControlAdapter();
            services.Add<INodeEnricher>(enricher, enricher.Priority);
            services.Add<ITextControlAdapter>(text, text.Priority);
        }
    }
}
