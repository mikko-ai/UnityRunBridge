using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using UnityEditor;
using UnityEngine;

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
    /// 监听指针点击与输入框失焦，转成语义动作。
    /// 指针输入经 IPointerInputBackend（只选 Priority 最高的一个，禁止双录）；
    /// 点击目标与当前选中经 IRecordingSemanticBackend；文本经 ITextControlAdapter 链。
    /// Features 不直接引用 EventSystems / InputSystem / UGUI。
    /// </summary>
    internal static class RecordingListener
    {
        private static Action<RecordedAction> onActionRecorded;
        private static GameObject pendingDownTarget;
        private static Vector2 pendingDownScreenPos;
        private static GameObject lastSelected;
        private static float startRealtime;
        private static IBridgeServiceResolver services;

        internal static bool IsListening { get; private set; }

        /// <summary>是否存在可用的指针输入后端（Both 模式下只认最高优先级那一个）。</summary>
        internal static bool HasInputBackend
        {
            get
            {
                return TrySelectPointerBackend(BridgeServices.Current(services), out _);
            }
        }

        public static void StartListening(Action<RecordedAction> callback, IBridgeServiceResolver resolver = null)
        {
            if (IsListening)
            {
                return;
            }

            services = BridgeServices.Current(resolver);
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
            services = null;
        }

        private static void Tick()
        {
            IBridgeServiceResolver resolver = BridgeServices.Current(services);
            if (resolver == null || !resolver.TryGet(out IRecordingSemanticBackend semantic))
            {
                return;
            }

            // 无活动 EventSystem 时语义后端返回 false，与原先跳过本帧行为一致。
            if (!semantic.TryGetCurrentSelection(out GameObject currentSelected))
            {
                return;
            }

            if (!TrySelectPointerBackend(resolver, out IPointerInputBackend pointer))
            {
                return;
            }

            if (pointer.TryGetPointerDown(out Vector2 downPos))
            {
                ProcessPointerDown(downPos, resolver);
            }

            if (pointer.TryGetPointerUp(out Vector2 upPos))
            {
                ProcessPointerUp(upPos, resolver);
            }

            ProcessSelectionChanged(currentSelected, resolver);
        }

        internal static void ProcessPointerDown(Vector2 screenPos, IBridgeServiceResolver resolver = null)
        {
            resolver = BridgeServices.Current(resolver ?? services);
            pendingDownTarget = ResolveClickTarget(screenPos, resolver);
            pendingDownScreenPos = screenPos;
        }

        internal static void ProcessPointerUp(Vector2 screenPos, IBridgeServiceResolver resolver = null)
        {
            resolver = BridgeServices.Current(resolver ?? services);
            GameObject downTarget = pendingDownTarget;
            pendingDownTarget = null;

            if (downTarget == null)
            {
                return;
            }

            GameObject upTarget = ResolveClickTarget(screenPos, resolver);
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

        internal static void ProcessSelectionChanged(GameObject currentSelected, IBridgeServiceResolver resolver = null)
        {
            resolver = BridgeServices.Current(resolver ?? services);
            if (currentSelected == lastSelected)
            {
                return;
            }

            if (lastSelected != null && TryGetInputFieldText(lastSelected, out string text, resolver))
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

        internal static GameObject ResolveClickTarget(Vector2 screenPos, IBridgeServiceResolver resolver = null)
        {
            resolver = BridgeServices.Current(resolver ?? services);
            if (resolver == null || !resolver.TryGet(out IRecordingSemanticBackend semantic))
            {
                return null;
            }

            return semantic.ResolveClickTarget(screenPos);
        }

        internal static bool TryGetInputFieldText(GameObject go, out string text, IBridgeServiceResolver resolver = null)
        {
            text = null;
            resolver = BridgeServices.Current(resolver ?? services);
            if (resolver == null || go == null)
            {
                return false;
            }

            foreach (ITextControlAdapter adapter in resolver.GetAll<ITextControlAdapter>())
            {
                try
                {
                    // 只接受真正的输入框：UGUI InputField / TMP_InputField 的 TryGetText 会返回文本。
                    // Text 组件也会被 TryGetText 命中，但录制语义只关心可编辑输入框；
                    // 用组件名启发式：存在 InputField / TMP_InputField 才算。
                    if (!HasEditableInputField(go))
                    {
                        return false;
                    }

                    if (adapter.TryGetText(go, out text) && text != null)
                    {
                        return true;
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning(
                        $"Unity Agent Bridge: ITextControlAdapter {adapter.GetType().FullName} 录制读文本异常，已跳过：{ex.Message}");
                }
            }

            return false;
        }

        private static bool HasEditableInputField(GameObject go)
        {
            foreach (Component component in go.GetComponents<Component>())
            {
                if (component == null)
                {
                    continue;
                }

                string name = component.GetType().Name;
                if (name == "InputField" || name == "TMP_InputField")
                {
                    return true;
                }
            }

            return false;
        }

        /// <summary>
        /// Both 模式下只选 Priority 最高的一个 pointer backend，禁止同时轮询导致双录。
        /// GetAll 已按 priority 降序排列，取首个即可。
        /// </summary>
        internal static bool TrySelectPointerBackend(
            IBridgeServiceResolver resolver,
            out IPointerInputBackend backend)
        {
            backend = null;
            if (resolver == null)
            {
                return false;
            }

            IReadOnlyList<IPointerInputBackend> all = resolver.GetAll<IPointerInputBackend>();
            if (all == null || all.Count == 0)
            {
                return false;
            }

            backend = all[0];
            return backend != null;
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
            services = null;
        }
    }
}
