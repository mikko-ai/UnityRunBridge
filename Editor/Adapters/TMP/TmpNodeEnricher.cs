using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Adapters.TMP
{
    /// <summary>
    /// TMP 节点增强占位：文本字段由统一文本链（ITextControlAdapter）写入，
    /// 本 Enricher 不覆盖 UGUI 已拥有字段，也不重复写 text。
    /// </summary>
    internal sealed class TmpNodeEnricher : INodeEnricher
    {
        public int Priority => 50;

        public void EnrichSummary(GameObject target, JsonValue summary)
        {
            // 文本由 NodeSerializer 的 ITextControlAdapter 链统一写入；此处刻意不写字段。
        }

        public void EnrichInspection(GameObject target, JsonValue inspection)
        {
            // 同上：不覆盖 UGUI 的 effectiveInteractable 等字段。
        }
    }
}
