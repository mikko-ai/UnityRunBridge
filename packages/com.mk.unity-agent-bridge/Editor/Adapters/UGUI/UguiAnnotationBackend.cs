using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Adapters.UGUI
{
    /// <summary>
    /// UGUI 标注收集：扫描可射线命中的 Graphic，过滤 inactive / 不可达 / 被遮挡元素，
    /// 按 sortingOrder→siblingIndex→path 稳定排序后分配 A/B/C… 标签。
    /// </summary>
    internal sealed class UguiAnnotationBackend : IUiAnnotationBackend
    {
        public IReadOnlyList<UiAnnotationElement> CollectAnnotatableElements()
        {
            List<UiAnnotationElement> collected = new List<UiAnnotationElement>();
            if (EventSystem.current == null)
            {
                return collected;
            }

            Graphic[] graphics = UnityEngine.Object.FindObjectsOfType<Graphic>(includeInactive: false);
            HashSet<int> seen = new HashSet<int>();

            foreach (Graphic graphic in graphics)
            {
                if (graphic == null || !graphic.raycastTarget || !graphic.isActiveAndEnabled)
                {
                    continue;
                }

                GameObject go = graphic.gameObject;
                if (!go.activeInHierarchy || !(go.transform is RectTransform rectTransform))
                {
                    continue;
                }

                if (!UguiGeometry.TryComputeScreenRect(rectTransform, out Rect rect) ||
                    rect.width < 1f ||
                    rect.height < 1f)
                {
                    continue;
                }

                // 跳过完全在屏幕外的元素
                if (rect.xMax < 0f || rect.yMax < 0f ||
                    rect.xMin > Screen.width || rect.yMin > Screen.height)
                {
                    continue;
                }

                // 以中心点射线：顶层命中必须是自身或子孙，否则视为被遮挡
                Vector2 center = rect.center;
                if (!IsRaycastReachable(go, center))
                {
                    continue;
                }

                int instanceId = go.GetInstanceID();
                if (!seen.Add(instanceId))
                {
                    continue;
                }

                Canvas canvas = graphic.canvas;
                int sortingOrder = canvas != null ? canvas.sortingOrder : 0;
                ClassifyElement(go, out string type, out string interaction);

                collected.Add(new UiAnnotationElement
                {
                    Name = go.name,
                    Path = NodePath.BuildPath(go.transform),
                    Type = type,
                    Interaction = interaction,
                    ScreenX = center.x,
                    ScreenY = center.y,
                    BoundsMinX = rect.xMin,
                    BoundsMinY = rect.yMin,
                    BoundsMaxX = rect.xMax,
                    BoundsMaxY = rect.yMax,
                    Interactable = UguiGeometry.ComputeEffectiveInteractable(go),
                    SortingOrder = sortingOrder,
                    SiblingIndex = go.transform.GetSiblingIndex()
                });
            }

            collected.Sort(CompareStable);
            for (int i = 0; i < collected.Count; i++)
            {
                collected[i].Label = IndexToLabel(i);
            }

            return collected;
        }

        private static bool IsRaycastReachable(GameObject target, Vector2 screenPoint)
        {
            PointerEventData pointerData = new PointerEventData(EventSystem.current) { position = screenPoint };
            List<RaycastResult> results = new List<RaycastResult>();
            EventSystem.current.RaycastAll(pointerData, results);
            if (results.Count == 0)
            {
                return false;
            }

            GameObject hit = results[0].gameObject;
            return IsSelfOrDescendant(hit.transform, target.transform) ||
                   IsSelfOrDescendant(target.transform, hit.transform);
        }

        private static bool IsSelfOrDescendant(Transform node, Transform ancestor)
        {
            Transform current = node;
            while (current != null)
            {
                if (current == ancestor)
                {
                    return true;
                }

                current = current.parent;
            }

            return false;
        }

        private static void ClassifyElement(GameObject go, out string type, out string interaction)
        {
            if (go.GetComponent<Button>() != null)
            {
                type = "Button";
                interaction = "click";
                return;
            }

            if (go.GetComponent<Toggle>() != null)
            {
                type = "Toggle";
                interaction = "toggle";
                return;
            }

            if (go.GetComponent<Slider>() != null)
            {
                type = "Slider";
                interaction = "drag";
                return;
            }

            if (go.GetComponent<Scrollbar>() != null)
            {
                type = "Scrollbar";
                interaction = "drag";
                return;
            }

            if (go.GetComponent<ScrollRect>() != null)
            {
                type = "ScrollRect";
                interaction = "drag";
                return;
            }

            if (go.GetComponent<InputField>() != null)
            {
                type = "InputField";
                interaction = "input";
                return;
            }

            if (go.GetComponent<Dropdown>() != null)
            {
                type = "Dropdown";
                interaction = "click";
                return;
            }

            if (ExecuteEvents.GetEventHandler<IPointerClickHandler>(go) != null)
            {
                type = "Graphic";
                interaction = "click";
                return;
            }

            if (ExecuteEvents.GetEventHandler<IDragHandler>(go) != null)
            {
                type = "Graphic";
                interaction = "drag";
                return;
            }

            type = "Graphic";
            interaction = "unknown";
        }

        private static int CompareStable(UiAnnotationElement a, UiAnnotationElement b)
        {
            int byOrder = b.SortingOrder.CompareTo(a.SortingOrder);
            if (byOrder != 0)
            {
                return byOrder;
            }

            int bySibling = a.SiblingIndex.CompareTo(b.SiblingIndex);
            if (bySibling != 0)
            {
                return bySibling;
            }

            return string.CompareOrdinal(a.Path, b.Path);
        }

        /// <summary>0→A … 25→Z，26→AA …</summary>
        internal static string IndexToLabel(int index)
        {
            if (index < 0)
            {
                return "?";
            }

            index++;
            char[] buffer = new char[8];
            int pos = buffer.Length;
            while (index > 0)
            {
                index--;
                buffer[--pos] = (char)('A' + (index % 26));
                index /= 26;
            }

            return new string(buffer, pos, buffer.Length - pos);
        }
    }
}
