using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace UnityRunBridge.Examples
{
    public sealed class UiReviewDemo : MonoBehaviour
    {
        private EventSystem events;
        private Canvas canvas;
        private GameObject dialog;
        private Button launcher;
        private Button confirm;
        private Button cancel;
        private Outline launcherFocus;
        private Outline confirmFocus;
        private Outline cancelFocus;
        private static UiReviewDemo instance;

        private void Awake()
        {
            instance = this;
            // The demo scene is empty except for this component. Its EventSystem
            // intentionally uses the built-in legacy input backend.
            events = new GameObject("ReviewEvents", typeof(EventSystem), typeof(StandaloneInputModule))
                .GetComponent<EventSystem>();

            var camera = new GameObject("ReviewCamera", typeof(Camera)).GetComponent<Camera>();
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color32(18, 27, 40, 255);
            camera.cullingMask = 0;

            canvas = new GameObject("ReviewCanvas", typeof(Canvas), typeof(CanvasScaler),
                typeof(GraphicRaycaster)).GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = canvas.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1280, 720);
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.Expand;

            RectTransform baseLayer = Panel("Background", canvas.transform, new Color32(18, 27, 40, 255),
                Vector2.zero, Vector2.one, Vector2.zero);
            baseLayer.GetComponent<Image>().raycastTarget = false;
            launcher = MakeButton("Open", canvas.transform, new Vector2(0, 0), new Vector2(300, 76),
                new Color32(37, 98, 168, 255));
            launcher.onClick.AddListener(Open);

            RectTransform shade = Panel("Dialog", canvas.transform, new Color32(5, 12, 19, 220),
                Vector2.zero, Vector2.one, Vector2.zero);
            dialog = shade.gameObject;
            RectTransform card = Panel("Card", shade, new Color32(35, 52, 72, 255),
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(420, 280));
            confirm = MakeButton("Confirm", card, new Vector2(0, 54), new Vector2(290, 72),
                new Color32(43, 120, 87, 255));
            cancel = MakeButton("Cancel", card, new Vector2(0, -54), new Vector2(290, 72),
                new Color32(74, 92, 118, 255));
            confirm.onClick.AddListener(Close);
            cancel.onClick.AddListener(Close);
            launcherFocus = launcher.GetComponent<Outline>();
            confirmFocus = confirm.GetComponent<Outline>();
            cancelFocus = cancel.GetComponent<Outline>();
            LinkNavigation(confirm, cancel);
            LinkNavigation(cancel, confirm);
            dialog.SetActive(false);
        }

        private void Start()
        {
            events.SetSelectedGameObject(launcher.gameObject);
        }

        private void LateUpdate()
        {
            var selected = events.currentSelectedGameObject;
            launcherFocus.enabled = selected == launcher.gameObject;
            confirmFocus.enabled = selected == confirm.gameObject;
            cancelFocus.enabled = selected == cancel.gameObject;
        }

        private void Open()
        {
            launcher.interactable = false;
            dialog.SetActive(true);
            events.SetSelectedGameObject(confirm.gameObject);
        }

        private void Close()
        {
            dialog.SetActive(false);
            launcher.interactable = true;
            events.SetSelectedGameObject(launcher.gameObject);
        }

        private void OnDestroy()
        {
            if (instance == this)
            {
                instance = null;
            }
        }

        // The two whitelist probes only observe the demo's own EventSystem and viewport.
        public static string FocusedControl()
        {
            if (instance == null || instance.events.currentSelectedGameObject == null)
            {
                return "<none>";
            }
            var selected = instance.events.currentSelectedGameObject;
            if (selected == instance.confirm.gameObject) return "confirm";
            if (selected == instance.cancel.gameObject) return "cancel";
            if (selected == instance.launcher.gameObject) return "launcher";
            return "<unexpected>";
        }

        public static string ViewportSize()
        {
            if (instance == null)
            {
                return "<none>";
            }
            Rect area = instance.canvas.pixelRect;
            return $"{Mathf.RoundToInt(area.width)}x{Mathf.RoundToInt(area.height)}";
        }

        private static void LinkNavigation(Button from, Button other)
        {
            from.navigation = new Navigation
            {
                mode = Navigation.Mode.Explicit,
                selectOnUp = other,
                selectOnDown = other
            };
        }

        private static RectTransform Panel(string name, Transform parent, Color color,
            Vector2 minAnchor, Vector2 maxAnchor, Vector2 size)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Image));
            var rect = go.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            rect.anchorMin = minAnchor;
            rect.anchorMax = maxAnchor;
            rect.sizeDelta = size;
            rect.anchoredPosition = Vector2.zero;
            go.GetComponent<Image>().color = color;
            return rect;
        }

        private static Button MakeButton(string name, Transform parent, Vector2 position, Vector2 size, Color color)
        {
            RectTransform rect = Panel(name, parent, color, Vector2.one * 0.5f, Vector2.one * 0.5f, size);
            rect.anchoredPosition = position;
            var button = rect.gameObject.AddComponent<Button>();
            button.targetGraphic = rect.GetComponent<Image>();
            ColorBlock palette = button.colors;
            palette.selectedColor = new Color32(190, 242, 255, 255);
            button.colors = palette;

            var outline = rect.gameObject.AddComponent<Outline>();
            outline.effectColor = new Color32(160, 230, 255, 255);
            outline.effectDistance = new Vector2(4, 4);
            outline.useGraphicAlpha = false;
            outline.enabled = false;

            var label = new GameObject("Label", typeof(RectTransform), typeof(Text)).GetComponent<Text>();
            label.rectTransform.SetParent(rect, false);
            label.rectTransform.anchorMin = Vector2.zero;
            label.rectTransform.anchorMax = Vector2.one;
            label.rectTransform.offsetMin = Vector2.zero;
            label.rectTransform.offsetMax = Vector2.zero;
            label.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            label.text = name;
            label.fontSize = 30;
            label.alignment = TextAnchor.MiddleCenter;
            label.color = Color.white;
            label.raycastTarget = false;
            return button;
        }
    }
}
