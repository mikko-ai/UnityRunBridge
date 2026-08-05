using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Capture
{
    /// <summary>
    /// 截图后处理标注：在 Texture2D 上绘制边框与 A/B/C 标签（内置 bitmap glyph，无字体依赖）。
    /// Texture2D 绘制使用左下原点；sidecar 转换为 PNG 左上原点，坐标可直接传给 capture/hit-test。
    /// </summary>
    internal static class ScreenshotAnnotationRenderer
    {
        private static readonly Color32 BorderColor = new Color32(255, 64, 64, 255);
        private static readonly Color32 LabelBgColor = new Color32(20, 20, 20, 220);
        private static readonly Color32 LabelFgColor = new Color32(255, 255, 255, 255);

        // 5x7 点阵，bit0=左上；仅覆盖 A-Z 与 0-9 用于多字符标签。
        private static readonly Dictionary<char, byte[]> Glyphs = BuildGlyphs();

        public static Texture2D Render(
            Texture2D source,
            IReadOnlyList<UiAnnotationElement> elements,
            out JsonValue sidecar,
            out float scale)
        {
            if (source == null)
            {
                throw new ArgumentNullException(nameof(source));
            }

            int width = source.width;
            int height = source.height;
            // source 已是输出尺寸（可能已降采样）；referenceScreen 记录当前 Screen，便于对照
            float refW = Screen.width > 0 ? Screen.width : width;
            float refH = Screen.height > 0 ? Screen.height : height;
            float scaleX = width / Mathf.Max(1f, refW);
            float scaleY = height / Mathf.Max(1f, refH);
            scale = Mathf.Min(scaleX, scaleY);

            Texture2D annotated = new Texture2D(width, height, TextureFormat.RGBA32, false);
            annotated.SetPixels32(source.GetPixels32());

            JsonValue elementsJson = JsonValue.NewArray();
            if (elements != null)
            {
                foreach (UiAnnotationElement element in elements)
                {
                    float unityMinX = element.BoundsMinX * scaleX;
                    float unityMinY = element.BoundsMinY * scaleY;
                    float unityMaxX = element.BoundsMaxX * scaleX;
                    float unityMaxY = element.BoundsMaxY * scaleY;
                    float imageScreenX = element.ScreenX * scaleX;
                    float imageScreenY = height - element.ScreenY * scaleY;
                    float imageMinY = height - unityMaxY;
                    float imageMaxY = height - unityMinY;

                    // 裁剪到纹理边界
                    int x0 = Mathf.Clamp(Mathf.RoundToInt(unityMinX), 0, width - 1);
                    int y0 = Mathf.Clamp(Mathf.RoundToInt(unityMinY), 0, height - 1);
                    int x1 = Mathf.Clamp(Mathf.RoundToInt(unityMaxX), 0, width - 1);
                    int y1 = Mathf.Clamp(Mathf.RoundToInt(unityMaxY), 0, height - 1);
                    if (x1 > x0 && y1 > y0)
                    {
                        DrawRectBorder(annotated, x0, y0, x1, y1, 2, BorderColor);
                        DrawLabel(annotated, element.Label ?? "?", x0, y1, width, height);
                    }

                    JsonValue item = JsonValue.NewObject();
                    item["label"] = element.Label ?? string.Empty;
                    item["name"] = element.Name ?? string.Empty;
                    item["path"] = element.Path ?? string.Empty;
                    item["type"] = element.Type ?? string.Empty;
                    item["interaction"] = element.Interaction ?? string.Empty;
                    item["interactable"] = element.Interactable;
                    item["sortingOrder"] = element.SortingOrder;
                    item["screenX"] = imageScreenX;
                    item["screenY"] = imageScreenY;
                    JsonValue bounds = JsonValue.NewObject();
                    bounds["minX"] = unityMinX;
                    bounds["minY"] = imageMinY;
                    bounds["maxX"] = unityMaxX;
                    bounds["maxY"] = imageMaxY;
                    item["bounds"] = bounds;
                    elementsJson.Add(item);
                }
            }

            annotated.Apply();

            sidecar = JsonValue.NewObject();
            sidecar["schemaVersion"] = 1;
            sidecar["coordinateSpace"] = "image-top-left";
            JsonValue referenceScreen = JsonValue.NewObject();
            referenceScreen["width"] = refW;
            referenceScreen["height"] = refH;
            sidecar["referenceScreen"] = referenceScreen;
            JsonValue output = JsonValue.NewObject();
            output["width"] = width;
            output["height"] = height;
            sidecar["output"] = output;
            sidecar["scale"] = scale;
            sidecar["scaleX"] = scaleX;
            sidecar["scaleY"] = scaleY;
            sidecar["elements"] = elementsJson;
            return annotated;
        }

        /// <summary>图像坐标（左上原点）→ Unity 屏幕坐标（左下原点）。</summary>
        public static Vector2 ImageToUnityScreen(
            float imageX,
            float imageY,
            float imageWidth,
            float imageHeight,
            float screenWidth,
            float screenHeight)
        {
            float sx = imageWidth <= 0f ? 0f : imageX / imageWidth * screenWidth;
            float sy = imageHeight <= 0f
                ? 0f
                : (1f - imageY / imageHeight) * screenHeight;
            return new Vector2(sx, sy);
        }

        internal static void DrawRectBorder(Texture2D texture, int x0, int y0, int x1, int y1, int thickness, Color32 color)
        {
            for (int t = 0; t < thickness; t++)
            {
                DrawHLine(texture, x0, x1, y0 + t, color);
                DrawHLine(texture, x0, x1, y1 - t, color);
                DrawVLine(texture, y0, y1, x0 + t, color);
                DrawVLine(texture, y0, y1, x1 - t, color);
            }
        }

        internal static void DrawLabel(Texture2D texture, string text, int anchorX, int topY, int width, int height)
        {
            if (string.IsNullOrEmpty(text))
            {
                return;
            }

            const int glyphW = 5;
            const int glyphH = 7;
            const int pad = 2;
            const int gap = 1;
            int labelW = pad * 2 + text.Length * glyphW + Math.Max(0, text.Length - 1) * gap;
            int labelH = pad * 2 + glyphH;

            int lx = Mathf.Clamp(anchorX, 0, Math.Max(0, width - labelW));
            int ly = Mathf.Clamp(topY - labelH, 0, Math.Max(0, height - labelH));

            FillRect(texture, lx, ly, lx + labelW - 1, ly + labelH - 1, LabelBgColor);

            int cursorX = lx + pad;
            int cursorY = ly + pad;
            foreach (char ch in text.ToUpperInvariant())
            {
                DrawGlyph(texture, ch, cursorX, cursorY, LabelFgColor);
                cursorX += glyphW + gap;
            }
        }

        private static void DrawGlyph(Texture2D texture, char ch, int x, int y, Color32 color)
        {
            if (!Glyphs.TryGetValue(ch, out byte[] rows))
            {
                return;
            }

            for (int row = 0; row < rows.Length; row++)
            {
                byte bits = rows[row];
                for (int col = 0; col < 5; col++)
                {
                    if ((bits & (1 << (4 - col))) != 0)
                    {
                        // glyph 行 0 为顶部；Texture2D y 向上，故从 y+glyphH-1 向下画
                        SetPixelSafe(texture, x + col, y + (rows.Length - 1 - row), color);
                    }
                }
            }
        }

        private static void FillRect(Texture2D texture, int x0, int y0, int x1, int y1, Color32 color)
        {
            for (int y = y0; y <= y1; y++)
            {
                for (int x = x0; x <= x1; x++)
                {
                    SetPixelSafe(texture, x, y, color);
                }
            }
        }

        private static void DrawHLine(Texture2D texture, int x0, int x1, int y, Color32 color)
        {
            if (x1 < x0)
            {
                int tmp = x0;
                x0 = x1;
                x1 = tmp;
            }

            for (int x = x0; x <= x1; x++)
            {
                SetPixelSafe(texture, x, y, color);
            }
        }

        private static void DrawVLine(Texture2D texture, int y0, int y1, int x, Color32 color)
        {
            if (y1 < y0)
            {
                int tmp = y0;
                y0 = y1;
                y1 = tmp;
            }

            for (int y = y0; y <= y1; y++)
            {
                SetPixelSafe(texture, x, y, color);
            }
        }

        private static void SetPixelSafe(Texture2D texture, int x, int y, Color32 color)
        {
            if (x < 0 || y < 0 || x >= texture.width || y >= texture.height)
            {
                return;
            }

            texture.SetPixel(x, y, color);
        }

        private static Dictionary<char, byte[]> BuildGlyphs()
        {
            Dictionary<char, byte[]> map = new Dictionary<char, byte[]>();
            void G(char c, params byte[] rows) => map[c] = rows;

            G('A', 0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11);
            G('B', 0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E);
            G('C', 0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E);
            G('D', 0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E);
            G('E', 0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F);
            G('F', 0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10);
            G('G', 0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0E);
            G('H', 0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11);
            G('I', 0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E);
            G('J', 0x01, 0x01, 0x01, 0x01, 0x11, 0x11, 0x0E);
            G('K', 0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11);
            G('L', 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F);
            G('M', 0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11);
            G('N', 0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11);
            G('O', 0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E);
            G('P', 0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10);
            G('Q', 0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D);
            G('R', 0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11);
            G('S', 0x0E, 0x11, 0x10, 0x0E, 0x01, 0x11, 0x0E);
            G('T', 0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04);
            G('U', 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E);
            G('V', 0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04);
            G('W', 0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11);
            G('X', 0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11);
            G('Y', 0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04);
            G('Z', 0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F);
            G('0', 0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E);
            G('1', 0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E);
            G('2', 0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F);
            G('3', 0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E);
            G('4', 0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02);
            G('5', 0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E);
            G('6', 0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E);
            G('7', 0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08);
            G('8', 0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E);
            G('9', 0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C);
            return map;
        }
    }
}
