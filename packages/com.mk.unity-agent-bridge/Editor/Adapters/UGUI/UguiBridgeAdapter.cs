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
            UguiAnnotationBackend annotation = new UguiAnnotationBackend();
            UguiHitTestBackend hitTest = new UguiHitTestBackend();
            UguiInteractionGestureBackend gesture = new UguiInteractionGestureBackend();

            services.Add<INodeEnricher>(enricher, enricher.Priority);
            services.Add<ITextControlAdapter>(text, text.Priority);
            services.Add<IInteractionBackend>(interaction, 100);
            services.Add<IRecordingSemanticBackend>(recording, 100);
            services.Add<IUiAnnotationBackend>(annotation, 100);
            services.Add<IUiHitTestBackend>(hitTest, 100);
            services.Add<IInteractionGestureBackend>(gesture, 100);
        }
    }
}
