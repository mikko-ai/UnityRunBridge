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
    /// UI 标注收集契约：扫描当前场景中可交互且射线可达的 UI 元素，
    /// 返回不含可选包类型的 DTO。无 UGUI Adapter 时 Features 走降级路径。
    /// </summary>
    public interface IUiAnnotationBackend
    {
        IReadOnlyList<UiAnnotationElement> CollectAnnotatableElements();
    }

    /// <summary>
    /// UI 命中探测契约：对 Unity 屏幕坐标（左下原点）执行 EventSystem 射线，
    /// 返回有序命中列表。Features 不直接引用 EventSystem。
    /// </summary>
    public interface IUiHitTestBackend
    {
        IReadOnlyList<UiHitResult> Raycast(Vector2 screenPoint);
    }

    /// <summary>
    /// 跨帧手势后端契约：long-press / drag 的单步推进。
    /// Click 保持 IInteractionBackend 不变；本契约仅服务异步 Job 手势。
    /// </summary>
    public interface IInteractionGestureBackend
    {
        InteractionGestureSession BeginLongPress(GameObject target, float durationSeconds, bool force);

        InteractionGestureSession BeginDrag(
            GameObject target,
            float deltaX,
            float deltaY,
            float durationSeconds,
            int steps,
            bool force);

        /// <summary>推进一帧；返回 true 表示手势已结束（成功或失败结果已写入 session.Result）。</summary>
        bool Tick(InteractionGestureSession session);
        void Cancel(InteractionGestureSession session);
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
