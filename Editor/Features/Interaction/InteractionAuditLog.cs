using System;
using System.IO;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Interaction
{
    internal static class InteractionAuditLog
    {
        private const string FileName = "interaction-actions.jsonl";

        private static Func<string> directoryResolver = ArtifactPathGuard.ResolveArtifactDirectory;
        private static Action<string, string> appendText = (path, text) => File.AppendAllText(path, text);

        internal static JsonValue BuildRequestSummary(string action, JsonValue body)
        {
            JsonValue request = JsonValue.NewObject();
            if (body != null && body.TryGetString("path", out string path) &&
                !string.IsNullOrWhiteSpace(path))
            {
                request["path"] = path;
            }

            if (action == "click")
            {
                request["force"] = body != null && body.GetBoolean("force", false);
            }
            else if (action == "input")
            {
                request["submit"] = body != null && body.GetBoolean("submit", false);
                if (body != null && body.TryGetString("text", out string text))
                {
                    request["textLength"] = text.Length;
                }
            }
            else if (action == "set-value")
            {
                if (body != null && body.TryGetString("component", out string component) &&
                    !string.IsNullOrWhiteSpace(component))
                {
                    request["component"] = component;
                }

                JsonValue value = body != null && body.TryGet("value", out JsonValue item) ? item : null;
                AppendSafeValueSummary(request, value);
            }

            return request;
        }

        internal static void AppendFromResponse(
            string action,
            JsonValue request,
            string scene,
            object response,
            long durationMs)
        {
            try
            {
                JsonValue line = BuildLine(action, request, scene, response, durationMs);
                string path = Path.Combine(directoryResolver(), FileName);
                appendText(path, line.ToString() + "\n");
            }
            catch (Exception ex)
            {
                Debug.LogWarning(
                    $"Unity Agent Bridge: 写入 interaction-actions.jsonl 失败：{ex.Message}");
            }
        }

        internal static void SetHooksForTests(Func<string> resolver, Action<string, string> appender)
        {
            directoryResolver = resolver ?? ArtifactPathGuard.ResolveArtifactDirectory;
            appendText = appender ?? ((path, text) => File.AppendAllText(path, text));
        }

        internal static void ResetForTests()
        {
            directoryResolver = ArtifactPathGuard.ResolveArtifactDirectory;
            appendText = (path, text) => File.AppendAllText(path, text);
        }

        private static void AppendSafeValueSummary(JsonValue request, JsonValue value)
        {
            if (value == null)
            {
                request["valueKind"] = "invalid";
                return;
            }

            if (value.IsNumber)
            {
                request["valueKind"] = "number";
                request["value"] = value;
                return;
            }

            if (value.IsBoolean)
            {
                request["valueKind"] = "boolean";
                request["value"] = value;
                return;
            }

            if (value.IsString)
            {
                request["valueKind"] = "string";
                request["valueLength"] = value.AsString.Length;
                return;
            }

            if (IsNumericXYObject(value))
            {
                JsonValue summary = JsonValue.NewObject();
                summary["x"] = value["x"];
                summary["y"] = value["y"];
                request["valueKind"] = "object";
                request["value"] = summary;
                return;
            }

            request["valueKind"] = "unknown";
        }

        private static bool IsNumericXYObject(JsonValue value)
        {
            return value != null &&
                value.IsObject &&
                value.Count == 2 &&
                value.ContainsKey("x") &&
                value.ContainsKey("y") &&
                value["x"].IsNumber &&
                value["y"].IsNumber;
        }

        private static JsonValue BuildLine(
            string action,
            JsonValue request,
            string scene,
            object response,
            long durationMs)
        {
            ResponseInfo result = ExtractResponseInfo(response);
            JsonValue line = JsonValue.NewObject();
            line["time"] = DateTime.UtcNow.ToString("O");
            line["action"] = action ?? string.Empty;
            line["ok"] = result.Ok;
            line["code"] = result.Ok ? "ok" : result.Code;
            line["request"] = request ?? JsonValue.NewObject();
            if (!string.IsNullOrWhiteSpace(scene))
            {
                line["scene"] = scene;
            }

            if (!result.Ok && !string.IsNullOrWhiteSpace(result.Message))
            {
                line["message"] = result.Message;
            }

            AppendResultFields(line, action, result);
            line["durationMs"] = Math.Max(0, durationMs);
            line["playModeFrame"] = Application.isPlaying ? Time.frameCount : -1;
            line["activeScenePath"] = EditorSceneManager.GetActiveScene().path ?? string.Empty;
            return line;
        }

        private static ResponseInfo ExtractResponseInfo(object response)
        {
            if (response is BridgeResponse bridgeResponse)
            {
                return new ResponseInfo
                {
                    Ok = bridgeResponse.ok,
                    Code = string.IsNullOrWhiteSpace(bridgeResponse.code) ? "unknown_error" : bridgeResponse.code,
                    Message = bridgeResponse.message,
                    Json = null
                };
            }

            if (response is JsonValue jsonResponse)
            {
                return new ResponseInfo
                {
                    Ok = jsonResponse.GetBoolean("ok", false),
                    Code = NormalizeFailureCode(jsonResponse.GetString("code", null)),
                    Message = jsonResponse.GetString("message", null),
                    Json = jsonResponse
                };
            }

            return new ResponseInfo { Ok = false, Code = "unknown_error" };
        }

        private static void AppendResultFields(JsonValue line, string action, ResponseInfo result)
        {
            if (result.Json == null)
            {
                return;
            }

            if (action == "click")
            {
                if (result.Ok)
                {
                    CopyStringIfPresent(line, result.Json, "clicked");
                    CopyStringOrNullIfPresent(line, result.Json, "raycastHit");
                    CopyArrayIfPresent(line, result.Json, "events");
                    CopyBooleanIfPresent(line, result.Json, "forced");
                }
                else if (result.Code == "occluded")
                {
                    CopyStringIfPresent(line, result.Json, "blockedBy");
                }
            }
            else if (action == "set-value" && result.Ok)
            {
                CopyStringIfPresent(line, result.Json, "component");
            }
        }

        private static string NormalizeFailureCode(string code)
        {
            return string.IsNullOrWhiteSpace(code) ? "unknown_error" : code;
        }

        private static void CopyStringIfPresent(JsonValue destination, JsonValue source, string key)
        {
            if (source.TryGet(key, out JsonValue value) && value.IsString)
            {
                destination[key] = value;
            }
        }

        private static void CopyStringOrNullIfPresent(JsonValue destination, JsonValue source, string key)
        {
            if (source.TryGet(key, out JsonValue value) && (value.IsString || value.IsNull))
            {
                destination[key] = value;
            }
        }

        private static void CopyArrayIfPresent(JsonValue destination, JsonValue source, string key)
        {
            if (source.TryGet(key, out JsonValue value) && value.IsArray)
            {
                destination[key] = value;
            }
        }

        private static void CopyBooleanIfPresent(JsonValue destination, JsonValue source, string key)
        {
            if (source.TryGet(key, out JsonValue value) && value.IsBoolean)
            {
                destination[key] = value;
            }
        }

        private sealed class ResponseInfo
        {
            public bool Ok;
            public string Code;
            public string Message;
            public JsonValue Json;
        }
    }
}
