using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Json;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;

namespace Mk.UnityAgentBridge.Editor.Adapters.TMP
{
    /// <summary>
    /// TMP 强类型文本/设值适配：TMP_Text、TMP_InputField、TMP_Dropdown。
    /// Priority 低于 UGUI，保证 UGUI 优先再 TMP。
    /// </summary>
    internal sealed class TmpTextControlAdapter : ITextControlAdapter
    {
        public int Priority => 100;

        public bool TryGetText(GameObject target, out string text)
        {
            text = null;
            if (target == null)
            {
                return false;
            }

            TMP_Text tmpText = target.GetComponent<TMP_Text>();
            if (tmpText != null)
            {
                text = tmpText.text;
                return true;
            }

            TMP_InputField inputField = target.GetComponent<TMP_InputField>();
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

            TMP_InputField inputField = target.GetComponent<TMP_InputField>();
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

            // TMP_InputField 继承 Selectable；沿父链 CanvasGroup 判定与 UGUI 一致。
            if (!ComputeEffectiveInteractable(target))
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

            result = InteractionOperationResult.Success("TMP_InputField");
            return true;
        }

        public void CollectValueCandidates(GameObject target, IList<ValueControlCandidate> candidates)
        {
            if (target == null || candidates == null)
            {
                return;
            }

            TMP_Dropdown dropdown = target.GetComponent<TMP_Dropdown>();
            if (dropdown != null)
            {
                candidates.Add(new ValueControlCandidate("TMP_Dropdown", dropdown, this));
            }
        }

        public bool TrySetValue(ValueControlCandidate candidate, JsonValue value, out InteractionOperationResult result)
        {
            result = null;
            if (candidate == null || candidate.Adapter != this || candidate.Component == null)
            {
                return false;
            }

            if (candidate.ComponentName != "TMP_Dropdown")
            {
                return false;
            }

            if (value == null || !value.IsNumber)
            {
                result = InteractionOperationResult.Fail("invalid_argument", "TMP_Dropdown 的 value 必须是整数下标");
                return true;
            }

            ((TMP_Dropdown)candidate.Component).value = value.AsInt;
            result = InteractionOperationResult.Success("TMP_Dropdown");
            return true;
        }

        private static bool ComputeEffectiveInteractable(GameObject go)
        {
            TMP_InputField inputField = go.GetComponent<TMP_InputField>();
            if (inputField != null && !inputField.interactable)
            {
                return false;
            }

            Transform current = go.transform;
            while (current != null)
            {
                CanvasGroup canvasGroup = current.GetComponent<CanvasGroup>();
                if (canvasGroup != null && (!canvasGroup.interactable || !canvasGroup.blocksRaycasts))
                {
                    return false;
                }

                if (canvasGroup != null && canvasGroup.ignoreParentGroups)
                {
                    break;
                }

                current = current.parent;
            }

            return true;
        }
    }
}
