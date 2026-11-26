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
    /// UGUI 交互后端：射线验证 + StandaloneInputModule.ProcessMousePress 最小等价语义派发。
    /// 从旧 PointerSimulator 迁入。
    /// </summary>
    internal sealed class UguiInteractionBackend : IInteractionBackend, ICoordinateClickBackend, IIndexedClickBackend
    {
        public InteractionOperationResult Click(GameObject target, bool force) => ClickCore(target, force, null);

        public Component[] GetActiveClickHandlers(GameObject target)
        {
            if (target == null || !target.activeInHierarchy)
                return Array.Empty<Component>();
            var handlers = new List<Component>();
            foreach (Component candidate in target.GetComponents<Component>())
            {
                if (candidate != null && candidate is IPointerClickHandler &&
                    (!(candidate is Behaviour behaviour) || behaviour.isActiveAndEnabled))
                    handlers.Add(candidate);
            }
            return handlers.ToArray();
        }

        public bool MatchesClickHandlers(GameObject target, Component[] expected)
        {
            if (expected == null || expected.Length == 0)
                return false;
            Component[] current = GetActiveClickHandlers(target);
            if (current.Length != expected.Length)
                return false;
            for (int i = 0; i < current.Length; i++)
                if (current[i] != expected[i])
                    return false;
            return true;
        }

        public InteractionOperationResult ClickIndexed(GameObject target, Component[] expected)
        {
            if (!MatchesClickHandlers(target, expected))
                return InteractionOperationResult.Fail("ui_index_handler_mismatch", "当前节点的点击处理器与已核验集合不符");
            return ClickCore(target, false, expected);
        }

        private InteractionOperationResult ClickCore(GameObject target, bool force, Component[] expected)
        {
            EventSystem eventSystem = EventSystem.current;
            if (eventSystem == null)
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
            if (expected != null && !(rect.width > 0 && rect.height > 0 && Screen.width > 0 && Screen.height > 0
                && screenPoint.x >= 0 && screenPoint.x < Screen.width
                && screenPoint.y >= 0 && screenPoint.y < Screen.height))
                return InteractionOperationResult.Fail("ui_index_offscreen", "控件中心不在当前 Game View 屏幕内");

            string targetPath = expected != null ? NodePath.BuildPath(target.transform) : null;
            int sceneHandle = expected != null ? target.scene.handle : 0;
            int width = Screen.width, height = Screen.height;
            PointerEventData pointerData = BuildPointerEventData(screenPoint);

            List<RaycastResult> raycastResults = new List<RaycastResult>();
            eventSystem.RaycastAll(pointerData, raycastResults);
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

                if (expected != null)
                {
                    var raycast = raycastResults[0];
                    var canvas = hitObject.GetComponentInParent<Canvas>();
                    GameObject press = ExecuteEvents.GetEventHandler<IPointerDownHandler>(hitObject);
                    if (!(raycast.module is GraphicRaycaster) || canvas == null || canvas.rootCanvas.targetDisplay != 0
                        || (press != null && press != target))
                        return InteractionOperationResult.Fail("ui_index_handler_mismatch",
                            "最上层命中或 PointerDown 目标与索引控件不符");
                }

                if (!UguiGeometry.ComputeEffectiveInteractable(target))
                {
                    return InteractionOperationResult.Fail(
                        "not_interactable", "目标节点当前不可交互（interactable=false 或祖先 CanvasGroup 禁用）");
                }

                dispatchRoot = hitObject;
            }

            Func<bool> verify = null;
            if (expected != null)
            {
                verify = () =>
                {
                    if (target == null || eventSystem == null || EventSystem.current != eventSystem ||
                        Screen.width != width || Screen.height != height || target.scene.handle != sceneHandle ||
                        NodePath.BuildPath(target.transform) != targetPath || !MatchesClickHandlers(target, expected) ||
                        !UguiGeometry.ComputeEffectiveInteractable(target))
                        return false;
                    eventSystem.RaycastAll(pointerData, raycastResults);
                    if (raycastResults.Count == 0 || raycastResults[0].gameObject != hitObject ||
                        hitObject == null || !IsSelfOrDescendant(hitObject.transform, target.transform) ||
                        !(raycastResults[0].module is GraphicRaycaster))
                        return false;
                    var canvas = hitObject.GetComponentInParent<Canvas>();
                    var press = ExecuteEvents.GetEventHandler<IPointerDownHandler>(hitObject);
                    return canvas != null && canvas.rootCanvas.targetDisplay == 0 &&
                        ExecuteEvents.GetEventHandler<IPointerClickHandler>(hitObject) == target &&
                        (press == null || press == target);
                };
            }
            if (verify != null && !verify())
            {
                var rejected = InteractionOperationResult.Fail("click_not_dispatched", "目标在派发前发生变化，请重新观察");
                rejected.Events = new List<string>();
                return rejected;
            }
            InteractionOperationResult dispatched = DispatchClick(dispatchRoot, target, hitObject, pointerData, force, verify);
            if (expected != null && !dispatched.Events.Contains("pointerClick"))
            {
                dispatched.Ok = false;
                dispatched.ErrorCode = "click_not_dispatched";
                dispatched.ErrorMessage = "目标在派发期间改变或未收到 pointerClick；先检查已派发事件，不要自动重试";
                dispatched.Clicked = null;
            }
            return dispatched;
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

        private InteractionOperationResult DispatchClick(
            GameObject dispatchRoot, GameObject target, GameObject hitObject, PointerEventData pointerData,
            bool force, Func<bool> verifyIndexed = null)
        {
            pointerData.eligibleForClick = true;
            List<string> events = new List<string>();

            // Indexed clicks never switch responders if a hover listener changes the UI.
            bool indexed = verifyIndexed != null;
            if (ExecuteEvents.ExecuteHierarchy(dispatchRoot, pointerData, ExecuteEvents.pointerEnterHandler) != null || !indexed)
                events.Add("pointerEnter");
            bool dispatchAllowed = !indexed || verifyIndexed();
            GameObject downHandlerGo = dispatchAllowed
                ? ExecuteEvents.ExecuteHierarchy(dispatchRoot, pointerData, ExecuteEvents.pointerDownHandler)
                : null;
            if (downHandlerGo != null)
            {
                events.Add("pointerDown");
            }
            else if (dispatchAllowed && (!indexed || verifyIndexed()))
            {
                downHandlerGo = ExecuteEvents.GetEventHandler<IPointerClickHandler>(dispatchRoot);
                if (indexed && downHandlerGo != target)
                    downHandlerGo = null;
            }

            pointerData.pointerPress = downHandlerGo;

            if (downHandlerGo != null)
            {
                if (ExecuteEvents.Execute(downHandlerGo, pointerData, ExecuteEvents.pointerUpHandler) || !indexed)
                    events.Add("pointerUp");

                GameObject clickAtUpGo = ExecuteEvents.GetEventHandler<IPointerClickHandler>(dispatchRoot);
                if (clickAtUpGo == downHandlerGo
                    && (!indexed || (downHandlerGo == target && verifyIndexed()))
                    && ExecuteEvents.Execute(downHandlerGo, pointerData, ExecuteEvents.pointerClickHandler))
                {
                    events.Add("pointerClick");
                }
            }

            if (ExecuteEvents.ExecuteHierarchy(dispatchRoot, pointerData, ExecuteEvents.pointerExitHandler) != null || !indexed)
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
