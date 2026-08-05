using System;
using System.Collections.Generic;
using System.IO;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Capture
{
    /// <summary>
    /// POST /capture/screenshot：v1 只支持「Editor 交互模式 + Play Mode + Game View 可渲染」，
    /// 用 Unity 进程内 API 读自身 framebuffer，不触发 OS 级屏幕录制权限（TCC）。
    /// annotate=true 时额外写出标注 PNG 与 JSON sidecar，不向场景创建 GameObject。
    /// </summary>
    internal static class CaptureController
    {
        internal static object CaptureScreenshot(BridgeRequestContext ctx)
        {
            JsonValue body = ctx.Body;
            string reason = body != null && body.TryGetString("reason", out string reasonValue) ? reasonValue : "agent";
            int maxLongEdgeOverride = body != null && body.TryGetLong("maxLongEdge", out long overrideValue) ? (int)overrideValue : 0;
            string targetDirectoryRaw = body != null && body.TryGetString("targetDirectory", out string dirValue) ? dirValue : null;
            bool annotate = body != null && body.GetBoolean("annotate", false);

            BridgeProjectConfig.CaptureScreenshotSettings settings = BridgeProjectConfig.Load().ScreenshotCapture;

            if (!settings.Enabled)
            {
                return BridgeResponse.Failure("capture_disabled", "screenshot capture is disabled (capture.screenshot.enabled=false in config.json)");
            }

            if (reason == "agent" && !settings.AllowAgentRequest)
            {
                return BridgeResponse.Failure("agent_capture_denied", "agent-initiated screenshot capture is disabled (capture.screenshot.allowAgentRequest=false)");
            }

            if (!EditorApplication.isPlaying)
            {
                return BridgeResponse.Failure("capture_requires_play_mode", "screenshot capture requires Play Mode");
            }

            if (Application.isBatchMode)
            {
                return BridgeResponse.Failure("capture_unavailable", "screenshot capture is unavailable in batchmode (no Game View)");
            }

            string projectRoot = ArtifactPathGuard.GetProjectRoot();
            string targetDirectory = string.IsNullOrWhiteSpace(targetDirectoryRaw)
                ? ArtifactPathGuard.ResolveArtifactDirectory()
                : targetDirectoryRaw;

            if (!ArtifactPathGuard.IsAllowedArtifactPath(projectRoot, targetDirectory))
            {
                return BridgeResponse.Failure("invalid_argument", "targetDirectory must be under .unity-agent/sessions or .unity-agent/scratch");
            }

            if (!CaptureQuota.TryConsume("screenshot", settings.MaxPerSession, out int usedCount))
            {
                return BridgeResponse.Failure("capture_quota_exceeded", $"exceeded capture.screenshot.maxPerSession={settings.MaxPerSession} (used {usedCount})");
            }

            Directory.CreateDirectory(targetDirectory);
            string outputPath = ArtifactPathGuard.NextSequencedPath(targetDirectory, "screenshot", ".png");
            int maxLongEdge = maxLongEdgeOverride > 0 ? maxLongEdgeOverride : settings.MaxLongEdge;
            IBridgeServiceResolver services = BridgeServices.Current();

            JobStartResult start = JobManager.StartJob(
                "screenshot",
                handle => RunCaptureJob(handle, outputPath, maxLongEdge, annotate, services),
                timeoutSeconds: 10);
            if (!start.Ok)
            {
                return BridgeResponse.Failure(start.ErrorCode, start.ErrorMessage);
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["jobId"] = start.JobId;
            return response;
        }

        private static void RunCaptureJob(
            JobHandle handle,
            string outputPath,
            int maxLongEdge,
            bool annotate,
            IBridgeServiceResolver services)
        {
            EditorApplication.QueuePlayerLoopUpdate();
            JobManager.ScheduleEndOfFrame(() =>
            {
                Texture2D captured = null;
                Texture2D resized = null;
                Texture2D annotated = null;
                try
                {
                    captured = ScreenCapture.CaptureScreenshotAsTexture();
                    Texture2D output = captured;
                    int width = captured.width;
                    int height = captured.height;
                    int longEdge = Mathf.Max(width, height);
                    if (maxLongEdge > 0 && longEdge > maxLongEdge)
                    {
                        float resizeScale = (float)maxLongEdge / longEdge;
                        int newWidth = Mathf.Max(1, Mathf.RoundToInt(width * resizeScale));
                        int newHeight = Mathf.Max(1, Mathf.RoundToInt(height * resizeScale));
                        resized = ResizeBilinear(captured, newWidth, newHeight);
                        output = resized;
                        width = newWidth;
                        height = newHeight;
                    }

                    File.WriteAllBytes(outputPath, output.EncodeToPNG());

                    Dictionary<string, object> result = new Dictionary<string, object>
                    {
                        ["path"] = outputPath,
                        ["width"] = width,
                        ["height"] = height
                    };

                    if (annotate)
                    {
                        AppendAnnotations(result, output, outputPath, services, out annotated);
                    }

                    handle.Succeed(result);
                }
                catch (Exception ex)
                {
                    handle.Fail("capture_failed", ex.Message);
                }
                finally
                {
                    if (captured != null)
                    {
                        UnityEngine.Object.DestroyImmediate(captured);
                    }

                    if (resized != null)
                    {
                        UnityEngine.Object.DestroyImmediate(resized);
                    }

                    if (annotated != null)
                    {
                        UnityEngine.Object.DestroyImmediate(annotated);
                    }
                }
            });
        }

        private static void AppendAnnotations(
            Dictionary<string, object> result,
            Texture2D output,
            string outputPath,
            IBridgeServiceResolver services,
            out Texture2D annotated)
        {
            annotated = null;
            IUiAnnotationBackend annotationBackend = null;
            bool uguiAvailable = services != null && services.TryGet(out annotationBackend);
            IReadOnlyList<UiAnnotationElement> elements = uguiAvailable && annotationBackend != null
                ? annotationBackend.CollectAnnotatableElements()
                : Array.Empty<UiAnnotationElement>();

            annotated = ScreenshotAnnotationRenderer.Render(
                output, elements, out JsonValue sidecar, out float scale);

            string annotatedPath = DeriveSiblingPath(outputPath, ".annotated.png");
            string annotationsPath = DeriveSiblingPath(outputPath, ".annotations.json");

            if (!ArtifactPathGuard.IsAllowedArtifactPath(ArtifactPathGuard.GetProjectRoot(), annotatedPath) ||
                !ArtifactPathGuard.IsAllowedArtifactPath(ArtifactPathGuard.GetProjectRoot(), annotationsPath))
            {
                throw new InvalidOperationException("annotation artifact path must stay under .unity-agent/sessions or scratch");
            }

            File.WriteAllBytes(annotatedPath, annotated.EncodeToPNG());
            File.WriteAllText(annotationsPath, sidecar.ToString());

            sidecar.TryGetObject("referenceScreen", out JsonValue referenceScreen);
            result["annotatedPath"] = annotatedPath;
            result["annotationsPath"] = annotationsPath;
            result["coordinateSpace"] = sidecar.GetString("coordinateSpace", "image-top-left");
            result["scale"] = scale;
            if (referenceScreen != null)
            {
                result["referenceScreen"] = new Dictionary<string, object>
                {
                    ["width"] = referenceScreen.GetDouble("width", 0),
                    ["height"] = referenceScreen.GetDouble("height", 0)
                };
            }

            result["annotationMeta"] = new Dictionary<string, object>
            {
                ["uguiAvailable"] = uguiAvailable,
                ["elementCount"] = elements.Count,
                ["schemaVersion"] = 1
            };
        }

        /// <summary>
        /// screenshot-1.png → screenshot-1.annotated.png / screenshot-1.annotations.json
        /// </summary>
        internal static string DeriveSiblingPath(string pngPath, string suffix)
        {
            if (pngPath.EndsWith(".png", StringComparison.OrdinalIgnoreCase))
            {
                return pngPath.Substring(0, pngPath.Length - 4) + suffix;
            }

            return pngPath + suffix;
        }

        /// <summary>双线性降采样；只在长边超过 maxLongEdge 时调用，v1 不做放大。</summary>
        internal static Texture2D ResizeBilinear(Texture2D source, int newWidth, int newHeight)
        {
            Texture2D result = new Texture2D(newWidth, newHeight, TextureFormat.RGBA32, false);
            for (int y = 0; y < newHeight; y++)
            {
                float v = newHeight <= 1 ? 0f : (float)y / (newHeight - 1);
                for (int x = 0; x < newWidth; x++)
                {
                    float u = newWidth <= 1 ? 0f : (float)x / (newWidth - 1);
                    result.SetPixel(x, y, source.GetPixelBilinear(u, v));
                }
            }

            result.Apply();
            return result;
        }
    }
}
