using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Adapters.UGUI
{
    /// <summary>
    /// UGUI 节点增强：拥有 interactable / effectiveInteractable / screenRect / alpha /
    /// renderMode / sortingOrder；不覆盖其他所有者已写字段；不写 text（由文本链统一写入）。
    /// </summary>
    internal sealed class UguiNodeEnricher : INodeEnricher
    {
        public int Priority => 100;

        public void EnrichSummary(GameObject target, JsonValue summary)
        {
            if (target == null || summary == null || !summary.IsObject)
            {
                return;
            }

            if (!summary.ContainsKey("interactable") &&
                UguiGeometry.TryGetInteractable(target, out bool interactable))
            {
                summary["interactable"] = interactable;
            }

            if (!summary.ContainsKey("screenRect") &&
                target.transform is RectTransform rectTransform &&
                UguiGeometry.TryComputeScreenRect(rectTransform, out Rect rect))
            {
                JsonValue rectJson = JsonValue.NewObject();
                rectJson["x"] = rect.x;
                rectJson["y"] = rect.y;
                rectJson["w"] = rect.width;
                rectJson["h"] = rect.height;
                summary["screenRect"] = rectJson;
            }

            if (!summary.ContainsKey("alpha"))
            {
                CanvasGroup canvasGroup = target.GetComponent<CanvasGroup>();
                if (canvasGroup != null)
                {
                    summary["alpha"] = canvasGroup.alpha;
                }
            }

            if (!summary.ContainsKey("renderMode") || !summary.ContainsKey("sortingOrder"))
            {
                Canvas canvas = target.GetComponent<Canvas>();
                if (canvas != null)
                {
                    if (!summary.ContainsKey("renderMode"))
                    {
                        summary["renderMode"] = canvas.renderMode.ToString();
                    }

                    if (!summary.ContainsKey("sortingOrder"))
                    {
                        summary["sortingOrder"] = canvas.sortingOrder;
                    }
                }
            }
        }

        public void EnrichInspection(GameObject target, JsonValue inspection)
        {
            if (target == null || inspection == null || !inspection.IsObject)
            {
                return;
            }

            if (!inspection.ContainsKey("effectiveInteractable"))
            {
                inspection["effectiveInteractable"] = UguiGeometry.ComputeEffectiveInteractable(target);
            }

            if (!inspection.TryGetArray("components", out JsonValue components))
            {
                return;
            }

            foreach (JsonValue componentJson in components.Items)
            {
                if (componentJson == null || !componentJson.IsObject)
                {
                    continue;
                }

                if (!componentJson.TryGetString("type", out string typeName))
                {
                    continue;
                }

                if (typeName != typeof(Button).FullName)
                {
                    continue;
                }

                if (componentJson.ContainsKey("onClickListeners"))
                {
                    continue;
                }

                Button button = target.GetComponent<Button>();
                if (button != null)
                {
                    componentJson["onClickListeners"] = BuildPersistentListeners(button.onClick);
                }
            }
        }

        private static JsonValue BuildPersistentListeners(UnityEventBase unityEvent)
        {
            JsonValue listeners = JsonValue.NewArray();
            if (unityEvent == null)
            {
                return listeners;
            }

            int count = unityEvent.GetPersistentEventCount();
            for (int i = 0; i < count; i++)
            {
                Object eventTarget = unityEvent.GetPersistentTarget(i);
                string methodName = unityEvent.GetPersistentMethodName(i);
                JsonValue listener = JsonValue.NewObject();
                listener["target"] = eventTarget == null ? null : JsonValue.FromString(eventTarget.name);
                listener["method"] = methodName;
                listeners.Add(listener);
            }

            return listeners;
        }
    }
}
