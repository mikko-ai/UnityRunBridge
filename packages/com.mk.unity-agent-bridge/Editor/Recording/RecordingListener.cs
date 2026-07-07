using System;
using System.Collections.Generic;
using System.Reflection;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using UnityEditor;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
#if MK_HAS_INPUT_SYSTEM && ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace Mk.UnityAgentBridge.Editor.Recording
{
    /// <summary>一条录制到的语义动作，Time 是相对录制开始的秒数，Frame 是 Time.frameCount。</summary>
    internal sealed class RecordedAction
    {
        public float Time;
        public int Frame;
        public string Type;
        public string Scene;
        public string Path;
        public float ScreenX;
        public float ScreenY;
        public string Text;
    }

    /// <summary>
    /// 监听指针点击与输入框失焦，转成语义动作。用 <see cref="EditorApplication.update"/> 驱动而不是
    /// MonoBehaviour：Editor-only 程序集里的脚本无法通过 AddComponent 挂到 GameObject 上
    /// （Unity 会报 "Can't add script behaviour ... because it is an editor script"），
    /// 而 EditorApplication.update 在 Play Mode 下同样每帧触发，不需要任何隐藏 GameObject。
    /// 全局只有一个录制会话，因此用静态状态即可，不必是实例。
    /// Process* 方法 internal，供测试直接调用，不必真的模拟鼠标/触摸输入或等待 update 触发。
    /// </summary>
    internal static class RecordingListener
    {
        private static Action<RecordedAction> onActionRecorded;
        private static GameObject pendingDownTarget;
        private static Vector2 pendingDownScreenPos;
        private static GameObject lastSelected;
        private static float startRealtime;

        internal static bool IsListening { get; private set; }

        public static void StartListening(Action<RecordedAction> callback)
        {
            if (IsListening)
            {
                return;
            }

            onActionRecorded = callback;
            pendingDownTarget = null;
            lastSelected = null;
            startRealtime = Time.realtimeSinceStartup;
            IsListening = true;
            EditorApplication.update += Tick;
        }

        public static void StopListening()
        {
            if (!IsListening)
            {
                return;
            }

            EditorApplication.update -= Tick;
            IsListening = false;

            // 停止前把仍在编辑但尚未失焦的输入框收尾，避免丢失最后一条输入动作。
            ProcessSelectionChanged(null);
            onActionRecorded = null;
            pendingDownTarget = null;
            lastSelected = null;
        }

        private static void Tick()
        {
            if (EventSystem.current == null)
            {
                return;
            }

            if (TryGetPointerDown(out Vector2 downPos))
            {
                ProcessPointerDown(downPos);
            }

            if (TryGetPointerUp(out Vector2 upPos))
            {
                ProcessPointerUp(upPos);
            }

            ProcessSelectionChanged(EventSystem.current.currentSelectedGameObject);
        }

        internal static void ProcessPointerDown(Vector2 screenPos)
        {
            pendingDownTarget = ResolveClickTarget(screenPos);
            pendingDownScreenPos = screenPos;
        }

        internal static void ProcessPointerUp(Vector2 screenPos)
        {
            GameObject downTarget = pendingDownTarget;
            pendingDownTarget = null;

            if (downTarget == null)
            {
                return;
            }

            GameObject upTarget = ResolveClickTarget(screenPos);
            if (upTarget != downTarget)
            {
                return;
            }

            Emit(new RecordedAction
            {
                Time = Time.realtimeSinceStartup - startRealtime,
                Frame = Time.frameCount,
                Type = "click",
                Scene = NodePath.GetSceneDisplayName(downTarget),
                Path = NodePath.BuildPath(downTarget.transform),
                ScreenX = pendingDownScreenPos.x,
                ScreenY = pendingDownScreenPos.y
            });
        }

        internal static void ProcessSelectionChanged(GameObject currentSelected)
        {
            if (currentSelected == lastSelected)
            {
                return;
            }

            if (lastSelected != null && TryGetInputFieldText(lastSelected, out string text))
            {
                Emit(new RecordedAction
                {
                    Time = Time.realtimeSinceStartup - startRealtime,
                    Frame = Time.frameCount,
                    Type = "input",
                    Scene = NodePath.GetSceneDisplayName(lastSelected),
                    Path = NodePath.BuildPath(lastSelected.transform),
                    Text = text
                });
            }

            lastSelected = currentSelected;
        }

        private static void Emit(RecordedAction action)
        {
            onActionRecorded?.Invoke(action);
        }

        internal static GameObject ResolveClickTarget(Vector2 screenPos)
        {
            if (EventSystem.current == null)
            {
                return null;
            }

            PointerEventData pointerData = new PointerEventData(EventSystem.current) { position = screenPos };
            List<RaycastResult> results = new List<RaycastResult>();
            EventSystem.current.RaycastAll(pointerData, results);
            return results.Count == 0 ? null : ExecuteEvents.GetEventHandler<IPointerClickHandler>(results[0].gameObject);
        }

        internal static bool TryGetInputFieldText(GameObject go, out string text)
        {
            text = null;
            Component inputField = go.GetComponent<InputField>();
            if (inputField == null)
            {
                inputField = FindByFullName(go, "TMPro.TMP_InputField");
            }

            if (inputField == null)
            {
                return false;
            }

            PropertyInfo textProperty = inputField.GetType().GetProperty("text", BindingFlags.Public | BindingFlags.Instance);
            if (textProperty == null || !textProperty.CanRead)
            {
                return false;
            }

            text = textProperty.GetValue(inputField) as string ?? string.Empty;
            return true;
        }

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

        /// <summary>仅供 EditMode 测试使用：把静态状态重置为未监听，避免测试之间互相污染。</summary>
        internal static void ResetForTests()
        {
            if (IsListening)
            {
                EditorApplication.update -= Tick;
            }

            IsListening = false;
            onActionRecorded = null;
            pendingDownTarget = null;
            lastSelected = null;
        }

#if MK_HAS_INPUT_SYSTEM && ENABLE_INPUT_SYSTEM
        internal const bool HasInputBackend = true;

        private static bool TryGetPointerDown(out Vector2 position)
        {
            if (Mouse.current != null && Mouse.current.leftButton.wasPressedThisFrame)
            {
                position = Mouse.current.position.ReadValue();
                return true;
            }

            if (Touchscreen.current != null && Touchscreen.current.primaryTouch.press.wasPressedThisFrame)
            {
                position = Touchscreen.current.primaryTouch.position.ReadValue();
                return true;
            }

            position = default;
            return false;
        }

        private static bool TryGetPointerUp(out Vector2 position)
        {
            if (Mouse.current != null && Mouse.current.leftButton.wasReleasedThisFrame)
            {
                position = Mouse.current.position.ReadValue();
                return true;
            }

            if (Touchscreen.current != null && Touchscreen.current.primaryTouch.press.wasReleasedThisFrame)
            {
                position = Touchscreen.current.primaryTouch.position.ReadValue();
                return true;
            }

            position = default;
            return false;
        }
#elif ENABLE_LEGACY_INPUT_MANAGER
        internal const bool HasInputBackend = true;

        private static bool TryGetPointerDown(out Vector2 position)
        {
            if (Input.GetMouseButtonDown(0))
            {
                position = Input.mousePosition;
                return true;
            }

            position = default;
            return false;
        }

        private static bool TryGetPointerUp(out Vector2 position)
        {
            if (Input.GetMouseButtonUp(0))
            {
                position = Input.mousePosition;
                return true;
            }

            position = default;
            return false;
        }
#else
        internal const bool HasInputBackend = false;

        private static bool TryGetPointerDown(out Vector2 position)
        {
            position = default;
            return false;
        }

        private static bool TryGetPointerUp(out Vector2 position)
        {
            position = default;
            return false;
        }
#endif
    }
}
