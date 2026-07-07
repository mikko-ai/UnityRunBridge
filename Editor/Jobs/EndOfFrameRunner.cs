using System;
using System.Collections;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Jobs
{
    /// <summary>
    /// Play Mode 下用于承载 "yield return new WaitForEndOfFrame()" 的隐藏 MonoBehaviour。
    /// 只应通过 <see cref="JobManager.ScheduleEndOfFrame"/> 使用，不直接暴露给业务代码。
    /// </summary>
    internal sealed class EndOfFrameRunner : MonoBehaviour
    {
        private Action callback;

        public static void Schedule(Action callback)
        {
            GameObject go = new GameObject("UnityAgentBridge.EndOfFrameRunner")
            {
                hideFlags = HideFlags.HideAndDontSave
            };
            TempObjectRegistry.Track(go);

            EndOfFrameRunner runner = go.AddComponent<EndOfFrameRunner>();
            runner.callback = callback;
            runner.StartCoroutine(runner.RunEndOfFrame());
        }

        private IEnumerator RunEndOfFrame()
        {
            yield return new WaitForEndOfFrame();

            Action cb = callback;
            GameObject go = gameObject;
            TempObjectRegistry.Untrack(go);
            UnityEngine.Object.DestroyImmediate(go);
            cb?.Invoke();
        }
    }
}
