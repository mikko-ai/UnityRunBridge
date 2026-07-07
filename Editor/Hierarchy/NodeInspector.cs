using System;
using System.Reflection;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Hierarchy
{
    /// <summary>
    /// GET /hierarchy/inspect 的详细序列化：摘要节点字段 + 每个组件的公共实例属性/字段
    /// （基础类型给值，引用类型只给对象名/null，不递归）+ 少量特化组件补充信息。
    /// </summary>
    internal static class NodeInspector
    {
        public static JsonValue BuildInspect(Transform transform)
        {
            GameObject go = transform.gameObject;
            JsonValue node = NodeSerializer.BuildSummary(transform);
            node["effectiveInteractable"] = NodeSerializer.ComputeEffectiveInteractable(go);

            int serializationErrors = 0;
            JsonValue componentsArray = JsonValue.NewArray();
            foreach (Component component in go.GetComponents<Component>())
            {
                if (component == null)
                {
                    continue;
                }

                componentsArray.Add(BuildComponentJson(component, ref serializationErrors));
            }

            node["components"] = componentsArray;
            node["serializationErrors"] = serializationErrors;
            return node;
        }

        private static JsonValue BuildComponentJson(Component component, ref int serializationErrors)
        {
            Type type = component.GetType();
            JsonValue json = JsonValue.NewObject();
            json["type"] = type.FullName;
            if (component is Behaviour behaviour)
            {
                json["enabled"] = behaviour.enabled;
            }

            JsonValue properties = JsonValue.NewObject();
            foreach (PropertyInfo property in type.GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                if (!property.CanRead || property.GetIndexParameters().Length > 0)
                {
                    continue;
                }

                TryAddMember(properties, property.Name, () => property.GetValue(component), property.PropertyType, ref serializationErrors);
            }

            foreach (FieldInfo field in type.GetFields(BindingFlags.Public | BindingFlags.Instance))
            {
                TryAddMember(properties, field.Name, () => field.GetValue(component), field.FieldType, ref serializationErrors);
            }

            json["properties"] = properties;

            if (component is RectTransform rectTransform)
            {
                AddRectTransformDetails(json, rectTransform);
            }

            if (component is Button button)
            {
                json["onClickListeners"] = BuildPersistentListeners(button.onClick);
            }

            return json;
        }

        private static void TryAddMember(JsonValue target, string name, Func<object> getter, Type declaredType, ref int serializationErrors)
        {
            if (target.ContainsKey(name))
            {
                return;
            }

            try
            {
                object value = getter();
                target[name] = ConvertValueToJson(value, declaredType);
            }
            catch (Exception)
            {
                serializationErrors++;
            }
        }

        private static JsonValue ConvertValueToJson(object value, Type declaredType)
        {
            if (value == null)
            {
                return JsonValue.Null;
            }

            switch (value)
            {
                case bool boolValue:
                    return boolValue;
                case string stringValue:
                    return stringValue;
                case Enum enumValue:
                    return enumValue.ToString();
                case Vector2 vector2:
                {
                    JsonValue obj = JsonValue.NewObject();
                    obj["x"] = vector2.x;
                    obj["y"] = vector2.y;
                    return obj;
                }
                case Vector3 vector3:
                {
                    JsonValue obj = JsonValue.NewObject();
                    obj["x"] = vector3.x;
                    obj["y"] = vector3.y;
                    obj["z"] = vector3.z;
                    return obj;
                }
                case Color color:
                {
                    JsonValue obj = JsonValue.NewObject();
                    obj["r"] = color.r;
                    obj["g"] = color.g;
                    obj["b"] = color.b;
                    obj["a"] = color.a;
                    return obj;
                }
                case Rect rect:
                {
                    JsonValue obj = JsonValue.NewObject();
                    obj["x"] = rect.x;
                    obj["y"] = rect.y;
                    obj["w"] = rect.width;
                    obj["h"] = rect.height;
                    return obj;
                }
            }

            if (IsNumeric(value))
            {
                return JsonValue.FromDouble(Convert.ToDouble(value));
            }

            if (value is UnityEngine.Object unityObject)
            {
                return unityObject == null ? JsonValue.Null : JsonValue.FromString(unityObject.name);
            }

            if (declaredType != null && declaredType.IsClass)
            {
                return JsonValue.FromString(value.ToString());
            }

            return JsonValue.Null;
        }

        private static bool IsNumeric(object value)
        {
            return value is sbyte or byte or short or ushort or int or uint or long or ulong or float or double or decimal;
        }

        private static void AddRectTransformDetails(JsonValue json, RectTransform rectTransform)
        {
            Vector3[] corners = new Vector3[4];
            rectTransform.GetWorldCorners(corners);
            JsonValue worldCorners = JsonValue.NewArray();
            foreach (Vector3 corner in corners)
            {
                JsonValue point = JsonValue.NewObject();
                point["x"] = corner.x;
                point["y"] = corner.y;
                point["z"] = corner.z;
                worldCorners.Add(point);
            }

            json["worldCorners"] = worldCorners;
        }

        private static JsonValue BuildPersistentListeners(UnityEventBase unityEvent)
        {
            JsonValue listeners = JsonValue.NewArray();
            if (unityEvent == null)
            {
                return listeners;
            }

            int count = unityEvent.GetPersistentEventCount();
            for (int i = 0; i < count; i++)
            {
                UnityEngine.Object target = unityEvent.GetPersistentTarget(i);
                string methodName = unityEvent.GetPersistentMethodName(i);
                JsonValue listener = JsonValue.NewObject();
                listener["target"] = target == null ? null : JsonValue.FromString(target.name);
                listener["method"] = methodName;
                listeners.Add(listener);
            }

            return listeners;
        }
    }
}
