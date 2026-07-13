using Mk.UnityAgentBridge.Editor.Contracts;

namespace Mk.UnityAgentBridge.Editor.Adapters.UGUI
{
    /// <summary>
    /// UGUI Adapter：注册节点增强、文本控件、交互与录制语义后端。
    /// 构造与 RegisterServices 禁止订阅全局事件。
    /// </summary>
    [BridgeAdapter]
    public sealed class UguiBridgeAdapter : IBridgeAdapter
    {
        public int Priority => 100;

        public void RegisterServices(IBridgeServiceRegistry services)
        {
            UguiNodeEnricher enricher = new UguiNodeEnricher();
            UguiTextControlAdapter text = new UguiTextControlAdapter();
            UguiInteractionBackend interaction = new UguiInteractionBackend();
            UguiRecordingSemanticBackend recording = new UguiRecordingSemanticBackend();

            services.Add<INodeEnricher>(enricher, enricher.Priority);
            services.Add<ITextControlAdapter>(text, text.Priority);
            services.Add<IInteractionBackend>(interaction, 100);
            services.Add<IRecordingSemanticBackend>(recording, 100);
        }
    }
}
