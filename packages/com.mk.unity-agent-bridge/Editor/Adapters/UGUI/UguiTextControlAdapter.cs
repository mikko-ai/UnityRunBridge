using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Adapters.UGUI
{
    /// <summary>
    /// UGUI 文本/设值适配：InputField、Text、Slider/Toggle/Scrollbar/Dropdown/ScrollRect。
    /// Priority 高于 TMP，保证 input / text 链优先尝试 UGUI。
    /// </summary>
    internal sealed class UguiTextControlAdapter : ITextControlAdapter
    {
        public int Priority => 200;

        public bool TryGetText(GameObject target, out string text)
        {
            text = null;
            if (target == null)
            {
                return false;
            }

            Text uiText = target.GetComponent<Text>();
            if (uiText != null)
            {
                text = uiText.text;
                return true;
            }

            InputField inputField = target.GetComponent<InputField>();
            if (inputField != null)
            {
                text = inputField.text ?? string.Empty;
                return true;
            }

            return false;
        }

        public bool TrySetText(GameObject target, string text, bool submit, out InteractionOperationResult result)
        {
            result = null;
            if (target == null)
            {
                return false;
            }

            InputField inputField = target.GetComponent<InputField>();
            if (inputField == null)
            {
                return false;
            }

            if (EventSystem.current == null)
            {
                result = InteractionOperationResult.Fail("no_event_system", "scene 中没有可用的 EventSystem");
                return true;
            }

            if (!target.activeInHierarchy)
            {
                result = InteractionOperationResult.Fail("node_inactive", "目标节点不是 activeInHierarchy");
                return true;
            }

            if (!UguiGeometry.ComputeEffectiveInteractable(target))
            {
                result = InteractionOperationResult.Fail("not_interactable", "目标输入框当前不可交互");
                return true;
            }

            EventSystem.current.SetSelectedGameObject(target);
            inputField.text = text ?? string.Empty;

            if (submit)
            {
                inputField.onEndEdit?.Invoke(text ?? string.Empty);
                inputField.onSubmit?.Invoke(text ?? string.Empty);
                EventSystem.current.SetSelectedGameObject(null);
            }

            result = InteractionOperationResult.Success("InputField");
            return true;
        }

        public void CollectValueCandidates(GameObject target, IList<ValueControlCandidate> candidates)
        {
            if (target == null || candidates == null)
            {
                return;
            }

            Slider slider = target.GetComponent<Slider>();
            if (slider != null)
            {
                candidates.Add(new ValueControlCandidate("Slider", slider, this));
            }

            Toggle toggle = target.GetComponent<Toggle>();
            if (toggle != null)
            {
                candidates.Add(new ValueControlCandidate("Toggle", toggle, this));
            }

            Scrollbar scrollbar = target.GetComponent<Scrollbar>();
            if (scrollbar != null)
            {
                candidates.Add(new ValueControlCandidate("Scrollbar", scrollbar, this));
            }

            Dropdown dropdown = target.GetComponent<Dropdown>();
            if (dropdown != null)
            {
                candidates.Add(new ValueControlCandidate("Dropdown", dropdown, this));
            }

            ScrollRect scrollRect = target.GetComponent<ScrollRect>();
            if (scrollRect != null)
            {
                candidates.Add(new ValueControlCandidate("ScrollRect", scrollRect, this));
            }
        }

        public bool TrySetValue(ValueControlCandidate candidate, JsonValue value, out InteractionOperationResult result)
        {
            result = null;
            if (candidate == null || candidate.Adapter != this || candidate.Component == null)
            {
                return false;
            }

            switch (candidate.ComponentName)
            {
                case "Slider":
                    if (value == null || !value.IsNumber)
                    {
                        result = InteractionOperationResult.Fail("invalid_argument", "Slider 的 value 必须是数字");
                        return true;
                    }

                    ((Slider)candidate.Component).value = value.AsFloat;
                    result = InteractionOperationResult.Success("Slider");
                    return true;

                case "Scrollbar":
                    if (value == null || !value.IsNumber)
                    {
                        result = InteractionOperationResult.Fail("invalid_argument", "Scrollbar 的 value 必须是数字");
                        return true;
                    }

                    ((Scrollbar)candidate.Component).value = value.AsFloat;
                    result = InteractionOperationResult.Success("Scrollbar");
                    return true;

                case "Toggle":
                    if (value == null || !value.IsBoolean)
                    {
                        result = InteractionOperationResult.Fail("invalid_argument", "Toggle 的 value 必须是 bool");
                        return true;
                    }

                    ((Toggle)candidate.Component).isOn = value.AsBoolean;
                    result = InteractionOperationResult.Success("Toggle");
                    return true;

                case "Dropdown":
                    if (value == null || !value.IsNumber)
                    {
                        result = InteractionOperationResult.Fail("invalid_argument", "Dropdown 的 value 必须是整数下标");
                        return true;
                    }

                    ((Dropdown)candidate.Component).value = value.AsInt;
                    result = InteractionOperationResult.Success("Dropdown");
                    return true;

                case "ScrollRect":
                    if (value == null || !value.IsObject)
                    {
                        result = InteractionOperationResult.Fail("invalid_argument", "ScrollRect 的 value 必须是 { x, y }");
                        return true;
                    }

                    Vector2 normalizedPosition = new Vector2(
                        (float)value["x"].AsDouble,
                        (float)value["y"].AsDouble);
                    ((ScrollRect)candidate.Component).normalizedPosition = normalizedPosition;
                    result = InteractionOperationResult.Success("ScrollRect");
                    return true;

                default:
                    return false;
            }
        }
    }
}
