using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Jobs
{
    /// <summary>
    /// 统一清理钩子：job / 录制（2.3）/ profiling（4.1）创建的所有 HideAndDontSave 临时对象
    /// 都在此登记，domain reload、退出 Play Mode、Editor 退出三个时机统一销毁。
    /// 注意 Enter Play Mode Options 可能关闭 domain reload——"reload 打断"路径不触发时，
    /// playModeStateChanged 路径必须独立成立，因此三个钩子各自独立注册，不假设互斥。
    /// </summary>
    [InitializeOnLoad]
    internal static class TempObjectRegistry
    {
        public delegate void CleanupCallback(string reason);

        private static readonly HashSet<UnityEngine.Object> Tracked = new HashSet<UnityEngine.Object>();
        private static event CleanupCallback CleanupRequested;

        static TempObjectRegistry()
        {
            AssemblyReloadEvents.beforeAssemblyReload += () => Cleanup("domain_reload");
            EditorApplication.playModeStateChanged += OnPlayModeStateChanged;
            EditorApplication.quitting += () => Cleanup("editor_quitting");
        }

        public static void Track(UnityEngine.Object obj)
        {
            if (obj != null)
            {
                Tracked.Add(obj);
            }
        }

        public static void Untrack(UnityEngine.Object obj)
        {
            Tracked.Remove(obj);
        }

        public static void RegisterCleanupHandler(CleanupCallback callback)
        {
            CleanupRequested += callback;
        }

        private static void OnPlayModeStateChanged(PlayModeStateChange change)
        {
            if (change == PlayModeStateChange.ExitingPlayMode)
            {
                Cleanup("play_mode_exited");
            }
        }

        private static void Cleanup(string reason)
        {
            if (Tracked.Count > 0)
            {
                UnityEngine.Object[] snapshot = new UnityEngine.Object[Tracked.Count];
                Tracked.CopyTo(snapshot);
                Tracked.Clear();
                foreach (UnityEngine.Object obj in snapshot)
                {
                    if (obj != null)
                    {
                        UnityEngine.Object.DestroyImmediate(obj);
                    }
                }
            }

            CleanupRequested?.Invoke(reason);
        }
    }
}
