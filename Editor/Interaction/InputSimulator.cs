using System;
using System.Collections.Generic;
using System.Reflection;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Interaction
{
    /// <summary>文本输入（InputField/TMP_InputField）与受限设值通道（Slider/Toggle/... ）。</summary>
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
        }

        public static OperationResult SetText(GameObject target, string text, bool submit)
        {
            if (EventSystem.current == null)
            {
                return OperationResult.Fail("no_event_system", "scene 中没有可用的 EventSystem");
            }

            if (!target.activeInHierarchy)
            {
                return OperationResult.Fail("node_inactive", "目标节点不是 activeInHierarchy");
            }

            Component inputField = target.GetComponent<InputField>();
            if (inputField == null)
            {
                inputField = FindByFullName(target, "TMPro.TMP_InputField");
            }

            if (inputField == null)
            {
                return OperationResult.Fail("not_input_field", "目标节点没有 InputField 或 TMP_InputField 组件");
            }

            if (!NodeSerializer.ComputeEffectiveInteractable(target))
            {
                return OperationResult.Fail("not_interactable", "目标输入框当前不可交互");
            }

            EventSystem.current.SetSelectedGameObject(target);

            Type type = inputField.GetType();
            PropertyInfo textProperty = type.GetProperty("text", BindingFlags.Public | BindingFlags.Instance);
            if (textProperty == null || !textProperty.CanWrite)
            {
                return OperationResult.Fail("not_input_field", "输入框组件没有可写的 text 属性");
            }

            textProperty.SetValue(inputField, text ?? string.Empty);

            if (submit)
            {
                InvokeStringEvent(inputField, type, "onEndEdit", text ?? string.Empty);
                InvokeStringEvent(inputField, type, "onSubmit", text ?? string.Empty);
                EventSystem.current.SetSelectedGameObject(null);
            }

            return OperationResult.Success();
        }

        public static OperationResult SetValue(GameObject target, string componentHint, JsonValue value)
        {
            if (!target.activeInHierarchy)
            {
                return OperationResult.Fail("node_inactive", "目标节点不是 activeInHierarchy");
            }

            List<(string Name, Component Component)> candidates = CollectCandidates(target);

            (string Name, Component Component) chosen;
            if (!string.IsNullOrEmpty(componentHint))
            {
                int index = candidates.FindIndex(c => string.Equals(c.Name, componentHint, StringComparison.OrdinalIgnoreCase));
                if (index < 0)
                {
                    return OperationResult.Fail("unsupported_set_value",
                        $"目标节点上没有找到组件 '{componentHint}'；受支持的组件：{string.Join(", ", SupportedSetValueComponents)}");
                }

                chosen = candidates[index];
            }
            else
            {
                if (candidates.Count == 0)
                {
                    return OperationResult.Fail("unsupported_set_value",
                        $"目标节点上没有可设值的组件；受支持的组件：{string.Join(", ", SupportedSetValueComponents)}");
                }

                if (candidates.Count > 1)
                {
                    List<string> names = candidates.ConvertAll(c => c.Name);
                    return OperationResult.Fail("ambiguous_component",
                        $"目标节点上有多个可设值组件（{string.Join(", ", names)}），请显式指定 component 参数");
                }

                chosen = candidates[0];
            }

            if (!NodeSerializer.ComputeEffectiveInteractable(target))
            {
                return OperationResult.Fail("not_interactable", "目标节点当前不可交互");
            }

            return ApplyValue(chosen.Name, chosen.Component, value);
        }

        private static OperationResult ApplyValue(string componentName, Component component, JsonValue value)
        {
            switch (componentName)
            {
                case "Slider":
                    if (value == null || !value.IsNumber)
                    {
                        return OperationResult.Fail("invalid_argument", "Slider 的 value 必须是数字");
                    }

                    ((Slider)component).value = value.AsFloat;
                    return OperationResult.Success(componentName);

                case "Scrollbar":
                    if (value == null || !value.IsNumber)
                    {
                        return OperationResult.Fail("invalid_argument", "Scrollbar 的 value 必须是数字");
                    }

                    ((Scrollbar)component).value = value.AsFloat;
                    return OperationResult.Success(componentName);

                case "Toggle":
                    if (value == null || !value.IsBoolean)
                    {
                        return OperationResult.Fail("invalid_argument", "Toggle 的 value 必须是 bool");
                    }

                    ((Toggle)component).isOn = value.AsBoolean;
                    return OperationResult.Success(componentName);

                case "Dropdown":
                    if (value == null || !value.IsNumber)
                    {
                        return OperationResult.Fail("invalid_argument", "Dropdown 的 value 必须是整数下标");
                    }

                    ((Dropdown)component).value = value.AsInt;
                    return OperationResult.Success(componentName);

                case "TMP_Dropdown":
                    if (value == null || !value.IsNumber)
                    {
                        return OperationResult.Fail("invalid_argument", "TMP_Dropdown 的 value 必须是整数下标");
                    }

                    return SetReflectedProperty(component, "value", value.AsInt, componentName);

                case "ScrollRect":
                    if (value == null || !value.IsObject)
                    {
                        return OperationResult.Fail("invalid_argument", "ScrollRect 的 value 必须是 { x, y }");
                    }

                    Vector2 normalizedPosition = new Vector2(
                        (float)value["x"].AsDouble,
                        (float)value["y"].AsDouble);
                    ((ScrollRect)component).normalizedPosition = normalizedPosition;
                    return OperationResult.Success(componentName);

                default:
                    return OperationResult.Fail("unsupported_set_value", $"不支持的组件：{componentName}");
            }
        }

        private static List<(string Name, Component Component)> CollectCandidates(GameObject go)
        {
            List<(string, Component)> candidates = new List<(string, Component)>();

            Slider slider = go.GetComponent<Slider>();
            if (slider != null)
            {
                candidates.Add(("Slider", slider));
            }

            Toggle toggle = go.GetComponent<Toggle>();
            if (toggle != null)
            {
                candidates.Add(("Toggle", toggle));
            }

            Scrollbar scrollbar = go.GetComponent<Scrollbar>();
            if (scrollbar != null)
            {
                candidates.Add(("Scrollbar", scrollbar));
            }

            Dropdown dropdown = go.GetComponent<Dropdown>();
            if (dropdown != null)
            {
                candidates.Add(("Dropdown", dropdown));
            }

            ScrollRect scrollRect = go.GetComponent<ScrollRect>();
            if (scrollRect != null)
            {
                candidates.Add(("ScrollRect", scrollRect));
            }

            Component tmpDropdown = FindByFullName(go, "TMPro.TMP_Dropdown");
            if (tmpDropdown != null)
            {
                candidates.Add(("TMP_Dropdown", tmpDropdown));
            }

            return candidates;
        }

        private static OperationResult SetReflectedProperty(Component component, string propertyName, object value, string componentName)
        {
            PropertyInfo property = component.GetType().GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance);
            if (property == null || !property.CanWrite)
            {
                return OperationResult.Fail("unsupported_set_value", $"{componentName} 没有可写的 {propertyName} 属性");
            }

            try
            {
                property.SetValue(component, Convert.ChangeType(value, property.PropertyType));
            }
            catch (Exception ex)
            {
                return OperationResult.Fail("invalid_argument", $"设置 {componentName}.{propertyName} 失败：{ex.Message}");
            }

            return OperationResult.Success(componentName);
        }

        private static void InvokeStringEvent(object component, Type type, string memberName, string value)
        {
            // UGUI InputField 的 onEndEdit/onSubmit 是属性，TMP_InputField 部分版本是字段，两者都要探测。
            object eventObj = null;
            PropertyInfo property = type.GetProperty(memberName, BindingFlags.Public | BindingFlags.Instance);
            if (property != null && property.CanRead)
            {
                eventObj = property.GetValue(component);
            }
            else
            {
                FieldInfo field = type.GetField(memberName, BindingFlags.Public | BindingFlags.Instance);
                eventObj = field?.GetValue(component);
            }

            if (eventObj == null)
            {
                return;
            }

            MethodInfo invoke = eventObj.GetType().GetMethod("Invoke", new[] { typeof(string) });
            invoke?.Invoke(eventObj, new object[] { value });
        }

        /// <summary>按类型全名反射探测组件（供 TMP 等可选依赖使用，未安装时静默返回 null）。</summary>
        private static Component FindByFullName(GameObject go, string fullName)
        {
            foreach (Component component in go.GetComponents<Component>())
            {
                if (component == null)
                {
                    continue;
                }

                Type type = component.GetType();
                while (type != null)
                {
                    if (type.FullName == fullName)
                    {
                        return component;
                    }

                    type = type.BaseType;
                }
            }

            return null;
        }
    }
}
