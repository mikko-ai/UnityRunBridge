using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using UnityEngine;
using UnityEngine.EventSystems;

namespace Mk.UnityAgentBridge.Editor.Adapters.UGUI
{
    /// <summary>
    /// UGUI 命中探测：对 Unity 屏幕坐标（左下原点）执行 EventSystem.RaycastAll，
    /// 返回按深度排序的命中列表（深度越小越靠前）。
    /// </summary>
    internal sealed class UguiHitTestBackend : IUiHitTestBackend
    {
        public IReadOnlyList<UiHitResult> Raycast(Vector2 screenPoint)
        {
            List<UiHitResult> hits = new List<UiHitResult>();
            if (EventSystem.current == null)
            {
                return hits;
            }

            PointerEventData pointerData = new PointerEventData(EventSystem.current) { position = screenPoint };
            List<RaycastResult> results = new List<RaycastResult>();
            EventSystem.current.RaycastAll(pointerData, results);

            foreach (RaycastResult result in results)
            {
                if (result.gameObject == null)
                {
                    continue;
                }

                hits.Add(new UiHitResult
                {
                    Path = NodePath.BuildPath(result.gameObject.transform),
                    Name = result.gameObject.name,
                    Depth = result.depth,
                    Module = result.module != null ? result.module.GetType().Name : string.Empty,
                    SortingOrder = result.sortingOrder,
                    Distance = result.distance,
                    GameObject = result.gameObject
                });
            }

            return hits;
        }
    }
}
