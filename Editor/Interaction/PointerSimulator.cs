using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using UnityEngine;
using UnityEngine.EventSystems;

namespace Mk.UnityAgentBridge.Editor.Interaction
{
    /// <summary>
    /// 射线验证 + StandaloneInputModule.ProcessMousePress 最小等价语义派发。
    /// 不依赖 Play Mode 的帧循环——EventSystem.RaycastAll / ExecuteEvents 都是可在任意时机
    /// 直接调用的静态 API，调用方（InteractionController）负责校验 Play Mode 前置条件。
    /// </summary>
    internal static class PointerSimulator
    {
        public sealed class ClickResult
        {
            public bool Ok;
            public string ErrorCode;
            public string ErrorMessage;
            public GameObject Clicked;
            public GameObject RaycastHit;
            public List<string> Events;
            public bool Forced;

            public static ClickResult Fail(string code, string message)
            {
                return new ClickResult { Ok = false, ErrorCode = code, ErrorMessage = message };
            }

            public static ClickResult Success(GameObject clicked, GameObject raycastHit, List<string> events, bool forced)
            {
                return new ClickResult { Ok = true, Clicked = clicked, RaycastHit = raycastHit, Events = events, Forced = forced };
            }
        }

        public static ClickResult SimulateClick(GameObject target, bool force)
        {
            if (EventSystem.current == null)
            {
                return ClickResult.Fail("no_event_system", "scene 中没有可用的 EventSystem");
            }

            if (!target.activeInHierarchy)
            {
                return ClickResult.Fail("node_inactive", "目标节点不是 activeInHierarchy");
            }

            if (!(target.transform is RectTransform rectTransform) || !NodeSerializer.TryComputeScreenRect(rectTransform, out Rect rect))
            {
                return ClickResult.Fail("invalid_argument", "目标节点没有可计算的 RectTransform screenRect");
            }

            Vector2 screenPoint = rect.center;
            PointerEventData pointerData = BuildPointerEventData(screenPoint);

            List<RaycastResult> raycastResults = new List<RaycastResult>();
            EventSystem.current.RaycastAll(pointerData, raycastResults);
            GameObject hitObject = raycastResults.Count > 0 ? raycastResults[0].gameObject : null;
            if (raycastResults.Count > 0)
            {
                pointerData.pointerCurrentRaycast = raycastResults[0];
                pointerData.pointerPressRaycast = raycastResults[0];
            }

            GameObject dispatchRoot;
            if (force)
            {
                dispatchRoot = target;
            }
            else
            {
                if (hitObject == null)
                {
                    return ClickResult.Fail("no_click_handler", "目标位置的射线检测没有命中任何 UI 元素");
                }

                // 只要命中对象是 target 自身或其子孙（例如命中的是 Button 下的 Image 子物体），
                // 就认为视觉上命中了 target；此时再从命中对象向上冒泡寻找 IPointerClickHandler。
                // 如果命中对象既不是 target 也不在其子树内，说明另一个元素挡在了 target 前面——
                // 无论该元素本身是否实现点击处理，都应该判定为遮挡（occluded），而不是简单地因为
                // 挡住它的元素没有点击处理器就退化成「找不到点击处理器」。
                if (!IsSelfOrDescendant(hitObject.transform, target.transform))
                {
                    ClickResult occluded = ClickResult.Fail("occluded",
                        $"点击被 {NodePath.BuildPath(hitObject.transform)} 遮挡");
                    occluded.RaycastHit = hitObject;
                    return occluded;
                }

                GameObject responder = ExecuteEvents.GetEventHandler<IPointerClickHandler>(hitObject);
                if (responder == null || responder != target)
                {
                    return ClickResult.Fail("no_click_handler",
                        $"命中链上没有找到 IPointerClickHandler（命中元素：{NodePath.BuildPath(hitObject.transform)}）");
                }

                if (!NodeSerializer.ComputeEffectiveInteractable(target))
                {
                    return ClickResult.Fail("not_interactable", "目标节点当前不可交互（interactable=false 或祖先 CanvasGroup 禁用）");
                }

                dispatchRoot = hitObject;
            }

            pointerData.eligibleForClick = true;
            List<string> events = new List<string>();

            ExecuteEvents.ExecuteHierarchy(dispatchRoot, pointerData, ExecuteEvents.pointerEnterHandler);
            events.Add("pointerEnter");

            GameObject downHandlerGo = ExecuteEvents.ExecuteHierarchy(dispatchRoot, pointerData, ExecuteEvents.pointerDownHandler);
            if (downHandlerGo != null)
            {
                events.Add("pointerDown");
            }
            else
            {
                downHandlerGo = ExecuteEvents.GetEventHandler<IPointerClickHandler>(dispatchRoot);
            }

            pointerData.pointerPress = downHandlerGo;

            if (downHandlerGo != null)
            {
                ExecuteEvents.Execute(downHandlerGo, pointerData, ExecuteEvents.pointerUpHandler);
                events.Add("pointerUp");

                GameObject clickAtUpGo = ExecuteEvents.GetEventHandler<IPointerClickHandler>(dispatchRoot);
                if (clickAtUpGo == downHandlerGo)
                {
                    ExecuteEvents.Execute(downHandlerGo, pointerData, ExecuteEvents.pointerClickHandler);
                    events.Add("pointerClick");
                }
            }

            ExecuteEvents.ExecuteHierarchy(dispatchRoot, pointerData, ExecuteEvents.pointerExitHandler);
            events.Add("pointerExit");

            return ClickResult.Success(downHandlerGo != null ? downHandlerGo : target, hitObject, events, force);
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

        private static PointerEventData BuildPointerEventData(Vector2 screenPoint)
        {
            return new PointerEventData(EventSystem.current)
            {
                position = screenPoint,
                pressPosition = screenPoint,
                button = PointerEventData.InputButton.Left,
                clickCount = 1,
                clickTime = Time.unscaledTime,
                eligibleForClick = true
            };
        }
    }
}
