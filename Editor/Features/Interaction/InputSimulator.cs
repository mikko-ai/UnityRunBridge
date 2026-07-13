using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Interaction
{
    /// <summary>
    /// Features 侧文本/设值入口：经 <c>ITextControlAdapter</c> 链完成 input / set-value，不直接引用 UGUI/TMP。
    /// </summary>
    internal static class InputSimulator
    {
        private static readonly string[] SupportedSetValueComponents =
        {
            "Slider", "Toggle", "Scrollbar", "Dropdown", "TMP_Dropdown", "ScrollRect"
        };

        public sealed class OperationResult
        {
            public bool Ok;
            public string ErrorCode;
            public string ErrorMessage;
            public string ComponentType;

            public static OperationResult Fail(string code, string message)
            {
                return new OperationResult { Ok = false, ErrorCode = code, ErrorMessage = message };
            }

            public static OperationResult Success(string componentType = null)
            {
                return new OperationResult { Ok = true, ComponentType = componentType };
            }

            public static OperationResult From(InteractionOperationResult result)
            {
                if (result == null)
                {
                    return Fail("internal_error", "交互结果为空");
                }

                return result.Ok
                    ? Success(result.ComponentType)
                    : Fail(result.ErrorCode, result.ErrorMessage);
            }
        }

        public static OperationResult SetText(
            GameObject target,
            string text,
            bool submit,
            IBridgeServiceResolver services = null)
        {
            services = BridgeServices.Current(services);
            if (services == null)
            {
                return OperationResult.Fail("not_input_field", "目标节点没有 InputField 或 TMP_InputField 组件");
            }

            foreach (ITextControlAdapter adapter in services.GetAll<ITextControlAdapter>())
            {
                try
                {
                    if (adapter.TrySetText(target, text, submit, out InteractionOperationResult result))
                    {
                        return OperationResult.From(result);
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning(
                        $"Unity Agent Bridge: ITextControlAdapter {adapter.GetType().FullName} TrySetText 异常，已跳过：{ex.Message}");
                }
            }

            return OperationResult.Fail("not_input_field", "目标节点没有 InputField 或 TMP_InputField 组件");
        }

        public static OperationResult SetValue(
            GameObject target,
            string componentHint,
            JsonValue value,
            IBridgeServiceResolver services = null)
        {
            if (target == null)
            {
                return OperationResult.Fail("invalid_argument", "目标节点为空");
            }

            if (!target.activeInHierarchy)
            {
                return OperationResult.Fail("node_inactive", "目标节点不是 activeInHierarchy");
            }

            services = BridgeServices.Current(services);
            if (services == null)
            {
                return OperationResult.Fail(
                    "unsupported_set_value",
                    $"目标节点上没有可设值的组件；受支持的组件：{string.Join(", ", SupportedSetValueComponents)}");
            }

            List<ValueControlCandidate> candidates = new List<ValueControlCandidate>();
            foreach (ITextControlAdapter adapter in services.GetAll<ITextControlAdapter>())
            {
                try
                {
                    adapter.CollectValueCandidates(target, candidates);
                }
                catch (Exception ex)
                {
                    Debug.LogWarning(
                        $"Unity Agent Bridge: ITextControlAdapter {adapter.GetType().FullName} CollectValueCandidates 异常，已跳过：{ex.Message}");
                }
            }

            ValueControlCandidate chosen;
            if (!string.IsNullOrEmpty(componentHint))
            {
                int index = candidates.FindIndex(
                    c => string.Equals(c.ComponentName, componentHint, StringComparison.OrdinalIgnoreCase));
                if (index < 0)
                {
                    return OperationResult.Fail(
                        "unsupported_set_value",
                        $"目标节点上没有找到组件 '{componentHint}'；受支持的组件：{string.Join(", ", SupportedSetValueComponents)}");
                }

                chosen = candidates[index];
            }
            else
            {
                if (candidates.Count == 0)
                {
                    return OperationResult.Fail(
                        "unsupported_set_value",
                        $"目标节点上没有可设值的组件；受支持的组件：{string.Join(", ", SupportedSetValueComponents)}");
                }

                if (candidates.Count > 1)
                {
                    List<string> names = candidates.ConvertAll(c => c.ComponentName);
                    return OperationResult.Fail(
                        "ambiguous_component",
                        $"目标节点上有多个可设值组件（{string.Join(", ", names)}），请显式指定 component 参数");
                }

                chosen = candidates[0];
            }

            if (!NodeSerializer.ComputeEffectiveInteractable(target, services))
            {
                return OperationResult.Fail("not_interactable", "目标节点当前不可交互");
            }

            if (chosen.Adapter == null)
            {
                return OperationResult.Fail("unsupported_set_value", $"不支持的组件：{chosen.ComponentName}");
            }

            if (!chosen.Adapter.TrySetValue(chosen, value, out InteractionOperationResult setResult) || setResult == null)
            {
                return OperationResult.Fail("unsupported_set_value", $"不支持的组件：{chosen.ComponentName}");
            }

            return OperationResult.From(setResult);
        }
    }
}
