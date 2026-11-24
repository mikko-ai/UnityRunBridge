using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Adapters.UGUI
{
    /// <summary>
    /// UGUI 交互后端：射线验证 + StandaloneInputModule.ProcessMousePress 最小等价语义派发。
    /// 从旧 PointerSimulator 迁入。
    /// </summary>
    internal sealed class UguiInteractionBackend : IInteractionBackend, ICoordinateClickBackend
    {
        public InteractionOperationResult Click(GameObject target, bool force)
        {
            if (EventSystem.current == null)
            {
                return InteractionOperationResult.Fail("no_event_system", "scene 中没有可用的 EventSystem");
            }

            if (target == null)
            {
                return InteractionOperationResult.Fail("invalid_argument", "目标节点为空");
            }

            if (!target.activeInHierarchy)
            {
                return InteractionOperationResult.Fail("node_inactive", "目标节点不是 activeInHierarchy");
            }

            if (!(target.transform is RectTransform rectTransform) ||
                !UguiGeometry.TryComputeScreenRect(rectTransform, out Rect rect))
            {
                return InteractionOperationResult.Fail(
                    "invalid_argument", "目标节点没有可计算的 RectTransform screenRect");
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
                    return InteractionOperationResult.Fail(
                        "no_click_handler", "目标位置的射线检测没有命中任何 UI 元素");
                }

                // 只要命中对象是 target 自身或其子孙，就认为视觉上命中了 target；
                // 否则判定为遮挡（occluded）。
                if (!IsSelfOrDescendant(hitObject.transform, target.transform))
                {
                    InteractionOperationResult occluded = InteractionOperationResult.Fail(
                        "occluded",
                        $"点击被 {NodePath.BuildPath(hitObject.transform)} 遮挡");
                    occluded.RaycastHit = hitObject;
                    return occluded;
                }

                GameObject responder = ExecuteEvents.GetEventHandler<IPointerClickHandler>(hitObject);
                if (responder == null || responder != target)
                {
                    return InteractionOperationResult.Fail(
                        "no_click_handler",
                        $"命中链上没有找到 IPointerClickHandler（命中元素：{NodePath.BuildPath(hitObject.transform)}）");
                }

                if (!UguiGeometry.ComputeEffectiveInteractable(target))
                {
                    return InteractionOperationResult.Fail(
                        "not_interactable", "目标节点当前不可交互（interactable=false 或祖先 CanvasGroup 禁用）");
                }

                dispatchRoot = hitObject;
            }

            return DispatchClick(dispatchRoot, target, hitObject, pointerData, force);
        }

        public InteractionOperationResult ClickAt(Vector2 screenPoint)
        {
            EventSystem eventSystem = EventSystem.current;
            if (eventSystem == null)
            {
                return InteractionOperationResult.Fail("no_event_system", "scene 中没有可用的 EventSystem");
            }

            PointerEventData pointerData = BuildPointerEventData(screenPoint);
            List<RaycastResult> hits = new List<RaycastResult>();
            eventSystem.RaycastAll(pointerData, hits);
            if (hits.Count == 0 || !(hits[0].module is GraphicRaycaster) || hits[0].gameObject == null)
            {
                return InteractionOperationResult.Fail("no_click_handler", "当前位置最上层没有 UGUI 射线命中");
            }

            RaycastResult hit = hits[0];
            GameObject responder = ExecuteEvents.GetEventHandler<IPointerClickHandler>(hit.gameObject);
            GameObject pressHandler = ExecuteEvents.GetEventHandler<IPointerDownHandler>(hit.gameObject);
            if (responder == null || (pressHandler != null && pressHandler != responder))
            {
                return InteractionOperationResult.Fail("no_click_handler", "最上层命中链没有可派发的点击处理器");
            }

            if (!UguiGeometry.ComputeEffectiveInteractable(responder))
            {
                return InteractionOperationResult.Fail("not_interactable", "目标节点当前不可交互");
            }

            pointerData.pointerCurrentRaycast = hit;
            pointerData.pointerPressRaycast = hit;
            InteractionOperationResult result = DispatchClick(hit.gameObject, responder, hit.gameObject, pointerData, false);
            return result.Events.Contains("pointerClick")
                ? result
                : InteractionOperationResult.Fail("click_not_dispatched", "指针事件已处理，但目标未收到 pointerClick");
        }

        private static InteractionOperationResult DispatchClick(
            GameObject dispatchRoot, GameObject target, GameObject hitObject, PointerEventData pointerData, bool force)
        {
            pointerData.eligibleForClick = true;
            List<string> events = new List<string>();

            ExecuteEvents.ExecuteHierarchy(dispatchRoot, pointerData, ExecuteEvents.pointerEnterHandler);
            events.Add("pointerEnter");

            GameObject downHandlerGo = ExecuteEvents.ExecuteHierarchy(
                dispatchRoot, pointerData, ExecuteEvents.pointerDownHandler);
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
                if (clickAtUpGo == downHandlerGo &&
                    ExecuteEvents.Execute(downHandlerGo, pointerData, ExecuteEvents.pointerClickHandler))
                {
                    events.Add("pointerClick");
                }
            }

            ExecuteEvents.ExecuteHierarchy(dispatchRoot, pointerData, ExecuteEvents.pointerExitHandler);
            events.Add("pointerExit");

            return new InteractionOperationResult
            {
                Ok = true,
                Clicked = downHandlerGo != null ? downHandlerGo : target,
                RaycastHit = hitObject,
                Events = events,
                Forced = force,
                ScreenPoint = pointerData.position
            };
        }

        public bool ComputeEffectiveInteractable(GameObject target)
        {
            return target != null && UguiGeometry.ComputeEffectiveInteractable(target);
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
