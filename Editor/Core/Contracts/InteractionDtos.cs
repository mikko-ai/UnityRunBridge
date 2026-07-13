using System.Collections.Generic;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Contracts
{
    /// <summary>
    /// 交互操作结果 DTO：固定承载现有 Ok/ErrorCode/ErrorMessage/ComponentType 语义
    /// （对应旧 InputSimulator.OperationResult / PointerSimulator 结果的公共字段），
    /// 供 ITextControlAdapter/IInteractionBackend 跨程序集返回结果，不暴露可选包具体类型。
    /// Click 路径额外可选字段（Clicked/RaycastHit/Events/Forced）供 Interaction 结果映射使用。
    /// </summary>
    public sealed class InteractionOperationResult
    {
        public bool Ok;
        public string ErrorCode;
        public string ErrorMessage;
        public string ComponentType;

        /// <summary>Click 命中并派发的目标（可为 null）。</summary>
        public GameObject Clicked;

        /// <summary>射线检测命中对象（occluded 时也用于 blockedBy）。</summary>
        public GameObject RaycastHit;

        /// <summary>Click 派发过程中实际触发的事件名列表。</summary>
        public List<string> Events;

        /// <summary>是否为 force 点击。</summary>
        public bool Forced;

        public static InteractionOperationResult Fail(string code, string message)
        {
            return new InteractionOperationResult { Ok = false, ErrorCode = code, ErrorMessage = message };
        }

        public static InteractionOperationResult Success(string componentType = null)
        {
            return new InteractionOperationResult { Ok = true, ComponentType = componentType };
        }
    }

    /// <summary>
    /// 可设值控件候选 DTO：固定承载组件的公开名称、实际 Component 以及提供它的文本 Adapter，
    /// 不把 UGUI/TMP 等可选包的具体类型泄漏到 Core。set-value 收集所有候选后按现有规则选择。
    /// </summary>
    public sealed class ValueControlCandidate
    {
        public string ComponentName;
        public Component Component;
        public ITextControlAdapter Adapter;

        public ValueControlCandidate()
        {
        }

        public ValueControlCandidate(string componentName, Component component, ITextControlAdapter adapter)
        {
            ComponentName = componentName;
            Component = component;
            Adapter = adapter;
        }
    }
}
