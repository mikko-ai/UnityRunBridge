using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using UnityEngine;
using UnityEngine.EventSystems;

namespace Mk.UnityAgentBridge.Editor.Adapters.UGUI
{
    /// <summary>UGUI 录制语义后端：EventSystem 射线解析点击目标与当前选中。</summary>
    internal sealed class UguiRecordingSemanticBackend : IRecordingSemanticBackend
    {
        public GameObject ResolveClickTarget(Vector2 screenPosition)
        {
            if (EventSystem.current == null)
            {
                return null;
            }

            PointerEventData pointerData = new PointerEventData(EventSystem.current) { position = screenPosition };
            List<RaycastResult> results = new List<RaycastResult>();
            EventSystem.current.RaycastAll(pointerData, results);
            return results.Count == 0
                ? null
                : ExecuteEvents.GetEventHandler<IPointerClickHandler>(results[0].gameObject);
        }

        public bool TryGetCurrentSelection(out GameObject currentSelected)
        {
            if (EventSystem.current == null)
            {
                currentSelected = null;
                return false;
            }

            currentSelected = EventSystem.current.currentSelectedGameObject;
            return true;
        }
    }
}
