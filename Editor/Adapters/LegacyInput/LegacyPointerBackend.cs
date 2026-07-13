using Mk.UnityAgentBridge.Editor.Contracts;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Adapters.LegacyInput
{
    /// <summary>Legacy Input Manager 指针后端：Input.GetMouseButtonDown/Up，Priority 100。</summary>
    internal sealed class LegacyPointerBackend : IPointerInputBackend
    {
        public int Priority => 100;

        public bool TryGetPointerDown(out Vector2 position)
        {
            if (Input.GetMouseButtonDown(0))
            {
                position = Input.mousePosition;
                return true;
            }

            position = default;
            return false;
        }

        public bool TryGetPointerUp(out Vector2 position)
        {
            if (Input.GetMouseButtonUp(0))
            {
                position = Input.mousePosition;
                return true;
            }

            position = default;
            return false;
        }
    }
}
