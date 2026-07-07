using System;
using System.Reflection;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Hierarchy
{
    /// <summary>1.1 节点数据模型的序列化与组件感知增强字段。</summary>
    internal static class NodeSerializer
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

            string text = TryGetText(go);
            if (text != null)
            {
                node["text"] = text;
            }

            if (TryGetInteractable(go, out bool interactable))
            {
                node["interactable"] = interactable;
            }

            if (transform is RectTransform rectTransform && TryComputeScreenRect(rectTransform, out Rect rect))
            {
                JsonValue rectJson = JsonValue.NewObject();
                rectJson["x"] = rect.x;
                rectJson["y"] = rect.y;
                rectJson["w"] = rect.width;
                rectJson["h"] = rect.height;
                node["screenRect"] = rectJson;
            }

            CanvasGroup canvasGroup = go.GetComponent<CanvasGroup>();
            if (canvasGroup != null)
            {
                node["alpha"] = canvasGroup.alpha;
            }

            Canvas canvas = go.GetComponent<Canvas>();
            if (canvas != null)
            {
                node["renderMode"] = canvas.renderMode.ToString();
                node["sortingOrder"] = canvas.sortingOrder;
            }

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

        public static string TryGetText(GameObject go)
        {
            Text uiText = go.GetComponent<Text>();
            if (uiText != null)
            {
                return uiText.text;
            }

            foreach (Component component in go.GetComponents<Component>())
            {
                if (component == null)
                {
                    continue;
                }

                Type type = component.GetType();
                while (type != null)
                {
                    if (type.FullName == "TMPro.TMP_Text")
                    {
                        PropertyInfo textProperty = type.GetProperty("text", BindingFlags.Public | BindingFlags.Instance);
                        if (textProperty == null)
                        {
                            return null;
                        }

                        try
                        {
                            return textProperty.GetValue(component) as string;
                        }
                        catch (Exception)
                        {
                            return null;
                        }
                    }

                    type = type.BaseType;
                }
            }

            return null;
        }

        public static bool TryGetInteractable(GameObject go, out bool interactable)
        {
            Selectable selectable = go.GetComponent<Selectable>();
            if (selectable != null)
            {
                interactable = selectable.interactable;
                return true;
            }

            interactable = false;
            return false;
        }

        /// <summary>
        /// 沿父链综合 Selectable.interactable 与所有祖先 CanvasGroup 的 interactable/blocksRaycasts
        /// 计算出的实际可交互结论（inspect 专用增强字段）。
        /// </summary>
        public static bool ComputeEffectiveInteractable(GameObject go)
        {
            if (TryGetInteractable(go, out bool selfInteractable) && !selfInteractable)
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

        public static bool TryComputeScreenRect(RectTransform rectTransform, out Rect rect)
        {
            rect = default;
            Vector3[] corners = new Vector3[4];
            rectTransform.GetWorldCorners(corners);

            Canvas canvas = rectTransform.GetComponentInParent<Canvas>();
            Vector2[] screenPoints = new Vector2[4];
            if (canvas == null || canvas.renderMode == RenderMode.ScreenSpaceOverlay)
            {
                for (int i = 0; i < 4; i++)
                {
                    screenPoints[i] = corners[i];
                }
            }
            else
            {
                Camera camera = canvas.worldCamera;
                for (int i = 0; i < 4; i++)
                {
                    screenPoints[i] = RectTransformUtility.WorldToScreenPoint(camera, corners[i]);
                }
            }

            float minX = screenPoints[0].x, maxX = screenPoints[0].x;
            float minY = screenPoints[0].y, maxY = screenPoints[0].y;
            for (int i = 1; i < 4; i++)
            {
                minX = Mathf.Min(minX, screenPoints[i].x);
                maxX = Mathf.Max(maxX, screenPoints[i].x);
                minY = Mathf.Min(minY, screenPoints[i].y);
                maxY = Mathf.Max(maxY, screenPoints[i].y);
            }

            rect = new Rect(minX, minY, maxX - minX, maxY - minY);
            return true;
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
