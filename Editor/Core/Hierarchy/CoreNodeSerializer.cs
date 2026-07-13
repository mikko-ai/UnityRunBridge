using System;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Hierarchy
{
    /// <summary>
    /// 通用节点序列化：仅输出 GameObject/Transform/component 的基础字段，不引用任何可选包
    /// （UGUI/TMP/Input System）。UGUI/TMP 等特有字段由 Adapter 的 <c>INodeEnricher</c> 追加；
    /// Features 层 <c>NodeSerializer</c> 负责编排 Core 摘要 + Enricher 链。
    /// </summary>
    public static class CoreNodeSerializer
    {
        public static JsonValue BuildSummary(Transform transform)
        {
            GameObject go = transform.gameObject;
            JsonValue node = JsonValue.NewObject();
            node["name"] = go.name;
            node["path"] = NodePath.BuildPath(transform);
            node["instanceId"] = go.GetInstanceID();
            node["scene"] = NodePath.GetSceneDisplayName(go);
            node["activeSelf"] = go.activeSelf;
            node["activeInHierarchy"] = go.activeInHierarchy;
            node["tag"] = SafeTag(go);
            node["layer"] = go.layer;
            node["componentTypes"] = BuildComponentTypeNames(go);
            node["childCount"] = transform.childCount;
            return node;
        }

        public static bool HasMissingScript(GameObject go)
        {
            foreach (Component component in go.GetComponents<Component>())
            {
                if (component == null)
                {
                    return true;
                }
            }

            return false;
        }

        private static JsonValue BuildComponentTypeNames(GameObject go)
        {
            JsonValue array = JsonValue.NewArray();
            foreach (Component component in go.GetComponents<Component>())
            {
                if (component != null)
                {
                    array.Add(component.GetType().Name);
                }
            }

            return array;
        }

        private static string SafeTag(GameObject go)
        {
            try
            {
                return go.tag;
            }
            catch (Exception)
            {
                return "Untagged";
            }
        }
    }
}
