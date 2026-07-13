using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Adapters.UGUI
{
    /// <summary>UGUI 几何与可交互性辅助，供 Interaction / Enricher 共用。</summary>
    internal static class UguiGeometry
    {
        public static bool TryGetInteractable(GameObject go, out bool interactable)
        {
            UnityEngine.UI.Selectable selectable = go.GetComponent<UnityEngine.UI.Selectable>();
            if (selectable != null)
            {
                interactable = selectable.interactable;
                return true;
            }

            interactable = false;
            return false;
        }

        public static bool ComputeEffectiveInteractable(GameObject go)
        {
            if (TryGetInteractable(go, out bool selfInteractable) && !selfInteractable)
            {
                return false;
            }

            Transform current = go.transform;
            while (current != null)
            {
                CanvasGroup canvasGroup = current.GetComponent<CanvasGroup>();
                if (canvasGroup != null && (!canvasGroup.interactable || !canvasGroup.blocksRaycasts))
                {
                    return false;
                }

                if (canvasGroup != null && canvasGroup.ignoreParentGroups)
                {
                    break;
                }

                current = current.parent;
            }

            return true;
        }

        public static bool TryComputeScreenRect(RectTransform rectTransform, out Rect rect)
        {
            rect = default;
            Vector3[] corners = new Vector3[4];
            rectTransform.GetWorldCorners(corners);

            Canvas canvas = rectTransform.GetComponentInParent<Canvas>();
            Vector2[] screenPoints = new Vector2[4];
            if (canvas == null || canvas.renderMode == RenderMode.ScreenSpaceOverlay)
            {
                for (int i = 0; i < 4; i++)
                {
                    screenPoints[i] = corners[i];
                }
            }
            else
            {
                Camera camera = canvas.worldCamera;
                for (int i = 0; i < 4; i++)
                {
                    screenPoints[i] = RectTransformUtility.WorldToScreenPoint(camera, corners[i]);
                }
            }

            float minX = screenPoints[0].x, maxX = screenPoints[0].x;
            float minY = screenPoints[0].y, maxY = screenPoints[0].y;
            for (int i = 1; i < 4; i++)
            {
                minX = Mathf.Min(minX, screenPoints[i].x);
                maxX = Mathf.Max(maxX, screenPoints[i].x);
                minY = Mathf.Min(minY, screenPoints[i].y);
                maxY = Mathf.Max(maxY, screenPoints[i].y);
            }

            rect = new Rect(minX, minY, maxX - minX, maxY - minY);
            return true;
        }
    }
}
