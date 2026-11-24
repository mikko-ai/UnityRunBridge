using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using UnityEngine;
using UnityEngine.EventSystems;

namespace Mk.UnityAgentBridge.Editor.Adapters.UGUI
{
    /// <summary>
    /// UGUI 跨帧手势：long-press / drag 事件序列。不修改现有 Click() 语义。
    /// long-press 默认不发 pointerClick；drag 走完整 drag 事件链。
    /// </summary>
    internal sealed class UguiInteractionGestureBackend : IInteractionGestureBackend
    {
        private sealed class LongPressState
        {
            public GameObject DispatchRoot;
            public GameObject DownHandler;
            public PointerEventData Pointer;
            public float Elapsed;
            public float Duration;
            public bool Pressed;
            public bool Force;
            public GameObject Target;
            public GameObject HitObject;
        }

        private sealed class DragState
        {
            public GameObject DispatchRoot;
            public GameObject DownHandler;
            public GameObject DragHandler;
            public PointerEventData Pointer;
            public Vector2 Start;
            public Vector2 End;
            public float Elapsed;
            public float Duration;
            public int Steps;
            public int StepIndex;
            public bool Started;
            public bool Force;
            public GameObject Target;
            public GameObject HitObject;
        }

        public InteractionGestureSession BeginLongPress(GameObject target, float durationSeconds, bool force)
        {
            InteractionGestureSession session = new InteractionGestureSession
            {
                Kind = "long-press",
                DurationSeconds = Mathf.Max(0.05f, durationSeconds)
            };

            if (!TryPreparePointer(target, force, session, out GameObject dispatchRoot, out GameObject hitObject,
                    out PointerEventData pointer, out GameObject downHandler))
            {
                session.Completed = true;
                return session;
            }

            session.StartScreenPoint = pointer.position;
            session.EndScreenPoint = pointer.position;
            session.State = new LongPressState
            {
                DispatchRoot = dispatchRoot,
                DownHandler = downHandler,
                Pointer = pointer,
                Duration = session.DurationSeconds,
                Force = force,
                Target = target,
                HitObject = hitObject
            };
            return session;
        }

        public InteractionGestureSession BeginDrag(
            GameObject target,
            float deltaX,
            float deltaY,
            float durationSeconds,
            int steps,
            bool force)
        {
            InteractionGestureSession session = new InteractionGestureSession
            {
                Kind = "drag",
                DurationSeconds = Mathf.Max(0.05f, durationSeconds)
            };

            if (!TryPreparePointer(target, force, session, out GameObject dispatchRoot, out GameObject hitObject,
                    out PointerEventData pointer, out GameObject downHandler))
            {
                session.Completed = true;
                return session;
            }

            int safeSteps = Mathf.Max(1, steps);
            Vector2 start = pointer.position;
            Vector2 end = start + new Vector2(deltaX, deltaY);
            session.StartScreenPoint = start;
            session.EndScreenPoint = end;
            session.State = new DragState
            {
                DispatchRoot = dispatchRoot,
                DownHandler = downHandler,
                Pointer = pointer,
                Start = start,
                End = end,
                Duration = session.DurationSeconds,
                Steps = safeSteps,
                Force = force,
                Target = target,
                HitObject = hitObject
            };
            return session;
        }

        public bool Tick(InteractionGestureSession session)
        {
            if (session == null || session.Completed)
            {
                return true;
            }

            if (session.State is LongPressState longPress)
            {
                return TickLongPress(session, longPress);
            }

            if (session.State is DragState drag)
            {
                return TickDrag(session, drag);
            }

            session.Completed = true;
            session.Result = InteractionOperationResult.Fail("internal_error", "未知手势状态");
            return true;
        }

        public void Cancel(InteractionGestureSession session)
        {
            if (session == null || session.Completed)
            {
                return;
            }

            if (session.State is LongPressState longPress && longPress.Pressed)
            {
                ReleasePointer(longPress.DispatchRoot, longPress.DownHandler, longPress.Pointer, session.Events);
            }
            else if (session.State is DragState drag && drag.Started)
            {
                FinishDrag(drag, session.Events, cancelled: true);
            }

            session.Completed = true;
            session.Result = InteractionOperationResult.Fail("cancelled", "手势已取消");
        }

        private static bool TickLongPress(InteractionGestureSession session, LongPressState state)
        {
            if (!state.Pressed)
            {
                ExecuteEvents.ExecuteHierarchy(state.DispatchRoot, state.Pointer, ExecuteEvents.pointerEnterHandler);
                session.Events.Add("pointerEnter");

                GameObject downGo = ExecuteEvents.ExecuteHierarchy(
                    state.DispatchRoot, state.Pointer, ExecuteEvents.pointerDownHandler);
                if (downGo != null)
                {
                    session.Events.Add("pointerDown");
                }
                else
                {
                    downGo = ExecuteEvents.GetEventHandler<IPointerDownHandler>(state.DispatchRoot)
                             ?? ExecuteEvents.GetEventHandler<IPointerClickHandler>(state.DispatchRoot);
                }

                state.DownHandler = downGo;
                state.Pointer.pointerPress = downGo;
                state.Pointer.eligibleForClick = false;
                state.Pressed = true;
                return false;
            }

            state.Elapsed += Time.unscaledDeltaTime;
            if (state.Elapsed < state.Duration)
            {
                return false;
            }

            if (state.DownHandler != null)
            {
                ExecuteEvents.Execute(state.DownHandler, state.Pointer, ExecuteEvents.pointerUpHandler);
                session.Events.Add("pointerUp");
            }

            ExecuteEvents.ExecuteHierarchy(state.DispatchRoot, state.Pointer, ExecuteEvents.pointerExitHandler);
            session.Events.Add("pointerExit");

            session.Completed = true;
            session.Result = new InteractionOperationResult
            {
                Ok = true,
                Clicked = state.DownHandler != null ? state.DownHandler : state.Target,
                RaycastHit = state.HitObject,
                Events = new List<string>(session.Events),
                Forced = state.Force
            };
            return true;
        }

        private static bool TickDrag(InteractionGestureSession session, DragState state)
        {
            if (!state.Started)
            {
                ExecuteEvents.ExecuteHierarchy(state.DispatchRoot, state.Pointer, ExecuteEvents.pointerEnterHandler);
                session.Events.Add("pointerEnter");

                GameObject downGo = ExecuteEvents.ExecuteHierarchy(
                    state.DispatchRoot, state.Pointer, ExecuteEvents.pointerDownHandler);
                if (downGo != null)
                {
                    session.Events.Add("pointerDown");
                }
                else
                {
                    downGo = ExecuteEvents.GetEventHandler<IPointerDownHandler>(state.DispatchRoot)
                             ?? ExecuteEvents.GetEventHandler<IDragHandler>(state.DispatchRoot);
                }

                state.DownHandler = downGo;
                state.Pointer.pointerPress = downGo;
                state.Pointer.eligibleForClick = false;

                GameObject dragHandler = ExecuteEvents.GetEventHandler<IDragHandler>(state.DispatchRoot)
                                         ?? downGo
                                         ?? state.Target;
                state.DragHandler = dragHandler;
                state.Pointer.pointerDrag = dragHandler;

                if (dragHandler != null)
                {
                    ExecuteEvents.Execute(dragHandler, state.Pointer, ExecuteEvents.initializePotentialDrag);
                    session.Events.Add("initializePotentialDrag");
                    ExecuteEvents.Execute(dragHandler, state.Pointer, ExecuteEvents.beginDragHandler);
                    session.Events.Add("beginDrag");
                }

                state.Started = true;
                return false;
            }

            state.Elapsed += Time.unscaledDeltaTime;
            float t = state.Duration <= 0f ? 1f : Mathf.Clamp01(state.Elapsed / state.Duration);
            int targetStep = Mathf.Min(state.Steps, Mathf.CeilToInt(t * state.Steps));
            while (state.StepIndex < targetStep)
            {
                state.StepIndex++;
                float stepT = (float)state.StepIndex / state.Steps;
                Vector2 pos = Vector2.Lerp(state.Start, state.End, stepT);
                Vector2 delta = pos - state.Pointer.position;
                state.Pointer.position = pos;
                state.Pointer.delta = delta;
                if (state.DragHandler != null)
                {
                    ExecuteEvents.Execute(state.DragHandler, state.Pointer, ExecuteEvents.dragHandler);
                    session.Events.Add("drag");
                }
            }

            if (state.Elapsed < state.Duration && state.StepIndex < state.Steps)
            {
                return false;
            }

            // 确保落到终点
            state.Pointer.position = state.End;
            state.Pointer.delta = Vector2.zero;
            FinishDrag(state, session.Events, cancelled: false);

            session.EndScreenPoint = state.End;
            session.Completed = true;
            session.Result = new InteractionOperationResult
            {
                Ok = true,
                Clicked = state.DragHandler != null ? state.DragHandler : state.Target,
                RaycastHit = state.HitObject,
                Events = new List<string>(session.Events),
                Forced = state.Force
            };
            return true;
        }

        private static void FinishDrag(DragState state, List<string> events, bool cancelled)
        {
            if (state.DragHandler != null)
            {
                ExecuteEvents.Execute(state.DragHandler, state.Pointer, ExecuteEvents.endDragHandler);
                events.Add("endDrag");
            }

            // 取消/超时只负责释放 pointer，不能触发具有业务副作用的 drop。
            if (!cancelled)
            {
                List<RaycastResult> results = new List<RaycastResult>();
                if (EventSystem.current != null)
                {
                    EventSystem.current.RaycastAll(state.Pointer, results);
                }

                if (results.Count > 0)
                {
                    GameObject dropTarget = ExecuteEvents.GetEventHandler<IDropHandler>(results[0].gameObject);
                    if (dropTarget != null)
                    {
                        ExecuteEvents.Execute(dropTarget, state.Pointer, ExecuteEvents.dropHandler);
                        events.Add("drop");
                    }
                }
            }

            if (state.DownHandler != null)
            {
                ExecuteEvents.Execute(state.DownHandler, state.Pointer, ExecuteEvents.pointerUpHandler);
                events.Add("pointerUp");
            }

            ExecuteEvents.ExecuteHierarchy(state.DispatchRoot, state.Pointer, ExecuteEvents.pointerExitHandler);
            events.Add("pointerExit");
            state.Pointer.pointerDrag = null;
            state.Pointer.pointerPress = null;
            state.Pointer.eligibleForClick = false;
        }

        private static void ReleasePointer(
            GameObject dispatchRoot,
            GameObject downHandler,
            PointerEventData pointer,
            List<string> events)
        {
            if (downHandler != null)
            {
                ExecuteEvents.Execute(downHandler, pointer, ExecuteEvents.pointerUpHandler);
                events.Add("pointerUp");
            }

            if (dispatchRoot != null)
            {
                ExecuteEvents.ExecuteHierarchy(dispatchRoot, pointer, ExecuteEvents.pointerExitHandler);
                events.Add("pointerExit");
            }
        }

        private static bool TryPreparePointer(
            GameObject target,
            bool force,
            InteractionGestureSession session,
            out GameObject dispatchRoot,
            out GameObject hitObject,
            out PointerEventData pointer,
            out GameObject downHandler)
        {
            dispatchRoot = null;
            hitObject = null;
            pointer = null;
            downHandler = null;

            if (EventSystem.current == null)
            {
                session.Result = InteractionOperationResult.Fail("no_event_system", "scene 中没有可用的 EventSystem");
                return false;
            }

            if (target == null)
            {
                session.Result = InteractionOperationResult.Fail("invalid_argument", "目标节点为空");
                return false;
            }

            if (!target.activeInHierarchy)
            {
                session.Result = InteractionOperationResult.Fail("node_inactive", "目标节点不是 activeInHierarchy");
                return false;
            }

            if (!(target.transform is RectTransform rectTransform) ||
                !UguiGeometry.TryComputeScreenRect(rectTransform, out Rect rect))
            {
                session.Result = InteractionOperationResult.Fail(
                    "invalid_argument", "目标节点没有可计算的 RectTransform screenRect");
                return false;
            }

            Vector2 screenPoint = rect.center;
            pointer = BuildPointerEventData(screenPoint);

            List<RaycastResult> raycastResults = new List<RaycastResult>();
            EventSystem.current.RaycastAll(pointer, raycastResults);
            hitObject = raycastResults.Count > 0 ? raycastResults[0].gameObject : null;
            if (raycastResults.Count > 0)
            {
                pointer.pointerCurrentRaycast = raycastResults[0];
                pointer.pointerPressRaycast = raycastResults[0];
            }

            if (force)
            {
                dispatchRoot = target;
            }
            else
            {
                if (hitObject == null)
                {
                    session.Result = InteractionOperationResult.Fail(
                        "no_click_handler", "目标位置的射线检测没有命中任何 UI 元素");
                    return false;
                }

                if (!IsSelfOrDescendant(hitObject.transform, target.transform))
                {
                    InteractionOperationResult occluded = InteractionOperationResult.Fail(
                        "occluded",
                        $"手势被 {NodePath.BuildPath(hitObject.transform)} 遮挡");
                    occluded.RaycastHit = hitObject;
                    session.Result = occluded;
                    return false;
                }

                if (!UguiGeometry.ComputeEffectiveInteractable(target))
                {
                    session.Result = InteractionOperationResult.Fail(
                        "not_interactable", "目标节点当前不可交互（interactable=false 或祖先 CanvasGroup 禁用）");
                    return false;
                }

                dispatchRoot = hitObject;
            }

            downHandler = null;
            return true;
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
                eligibleForClick = false
            };
        }
    }
}
