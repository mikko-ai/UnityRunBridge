using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Contracts
{
    /// <summary>
    /// 节点增强契约：在 Core 基础节点字段之上追加各技术特有字段（如 UGUI 的 interactable/
    /// screenRect 等）。按 Priority 排序执行，遵守字段所有权规则，不覆盖其他所有者已写字段。
    /// </summary>
    public interface INodeEnricher
    {
        int Priority { get; }
        void EnrichSummary(GameObject target, JsonValue summary);
        void EnrichInspection(GameObject target, JsonValue inspection);
    }

    /// <summary>
    /// 文本控件适配契约：读写文本、收集可设值候选并落值。多个实现按优先级逐个 Try，
    /// 直到有实现接受目标（不让某一实现全局覆盖其他）。
    /// </summary>
    public interface ITextControlAdapter
    {
        int Priority { get; }
        bool TryGetText(GameObject target, out string text);
        bool TrySetText(GameObject target, string text, bool submit, out InteractionOperationResult result);
        void CollectValueCandidates(GameObject target, IList<ValueControlCandidate> candidates);
        bool TrySetValue(ValueControlCandidate candidate, JsonValue value, out InteractionOperationResult result);
    }

    /// <summary>交互后端契约：点击与有效可交互判定。</summary>
    public interface IInteractionBackend
    {
        InteractionOperationResult Click(GameObject target, bool force);
        bool ComputeEffectiveInteractable(GameObject target);
    }

    /// <summary>
    /// 录制语义后端契约：把屏幕坐标解析为点击目标，并查询当前 UI 选中对象。
    /// EventSystem 等可选包细节留在 Adapter；Features 只经本契约访问。
    /// </summary>
    public interface IRecordingSemanticBackend
    {
        GameObject ResolveClickTarget(Vector2 screenPosition);

        /// <summary>
        /// 查询当前 UI 选中对象。无活动 EventSystem 时返回 false（录制 Tick 应跳过本帧）；
        /// 有 EventSystem 时返回 true，currentSelected 可为 null。
        /// </summary>
        bool TryGetCurrentSelection(out GameObject currentSelected);
    }

    /// <summary>指针输入后端契约：按优先级提供指针按下/抬起事件（Input System 200，Legacy 100）。</summary>
    public interface IPointerInputBackend
    {
        int Priority { get; }
        bool TryGetPointerDown(out Vector2 position);
        bool TryGetPointerUp(out Vector2 position);
    }
}
