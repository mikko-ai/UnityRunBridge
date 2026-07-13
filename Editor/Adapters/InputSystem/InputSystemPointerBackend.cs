using Mk.UnityAgentBridge.Editor.Contracts;
using UnityEngine;
using UnityEngine.InputSystem;

namespace Mk.UnityAgentBridge.Editor.Adapters.InputSystem
{
    /// <summary>Input System 指针后端：Mouse / Touchscreen，Priority 200（高于 Legacy）。</summary>
    internal sealed class InputSystemPointerBackend : IPointerInputBackend
    {
        public int Priority => 200;

        public bool TryGetPointerDown(out Vector2 position)
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

        public bool TryGetPointerUp(out Vector2 position)
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
    }
}
