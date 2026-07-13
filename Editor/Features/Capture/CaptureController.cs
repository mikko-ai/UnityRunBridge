using System;
using System.Collections.Generic;
using System.IO;
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
    /// </summary>
    internal static class CaptureController
    {
        internal static object CaptureScreenshot(BridgeRequestContext ctx)
        {
            JsonValue body = ctx.Body;
            string reason = body != null && body.TryGetString("reason", out string reasonValue) ? reasonValue : "agent";
            int maxLongEdgeOverride = body != null && body.TryGetLong("maxLongEdge", out long overrideValue) ? (int)overrideValue : 0;
            string targetDirectoryRaw = body != null && body.TryGetString("targetDirectory", out string dirValue) ? dirValue : null;

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

            JobStartResult start = JobManager.StartJob("screenshot", handle => RunCaptureJob(handle, outputPath, maxLongEdge), timeoutSeconds: 10);
            if (!start.Ok)
            {
                return BridgeResponse.Failure(start.ErrorCode, start.ErrorMessage);
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["jobId"] = start.JobId;
            return response;
        }

        private static void RunCaptureJob(JobHandle handle, string outputPath, int maxLongEdge)
        {
            EditorApplication.QueuePlayerLoopUpdate();
            JobManager.ScheduleEndOfFrame(() =>
            {
                Texture2D captured = null;
                Texture2D resized = null;
                try
                {
                    captured = ScreenCapture.CaptureScreenshotAsTexture();
                    Texture2D output = captured;
                    int width = captured.width;
                    int height = captured.height;
                    int longEdge = Mathf.Max(width, height);
                    if (maxLongEdge > 0 && longEdge > maxLongEdge)
                    {
                        float scale = (float)maxLongEdge / longEdge;
                        int newWidth = Mathf.Max(1, Mathf.RoundToInt(width * scale));
                        int newHeight = Mathf.Max(1, Mathf.RoundToInt(height * scale));
                        resized = ResizeBilinear(captured, newWidth, newHeight);
                        output = resized;
                        width = newWidth;
                        height = newHeight;
                    }

                    File.WriteAllBytes(outputPath, output.EncodeToPNG());

                    handle.Succeed(new Dictionary<string, object>
                    {
                        ["path"] = outputPath,
                        ["width"] = width,
                        ["height"] = height
                    });
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
                }
            });
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
