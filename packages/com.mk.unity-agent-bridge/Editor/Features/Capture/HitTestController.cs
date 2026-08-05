using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Capture
{
    /// <summary>
    /// POST /capture/hit-test：把公开图像坐标（左上原点）转为 Game View / Unity 屏幕坐标，
    /// 分别返回 UGUI 与 Physics3D 有序命中。挂在 capture module，不依赖 interaction capability。
    /// </summary>
    internal static class HitTestController
    {
        internal static object HitTest(BridgeRequestContext ctx, IBridgeServiceResolver services = null)
        {
            services = BridgeServices.Current(services);
            JsonValue body = ctx.Body;
            if (body == null)
            {
                return BridgeResponse.Failure("invalid_argument", "body 必须包含 x/y/imageWidth/imageHeight");
            }

            if (!body.TryGetDouble("x", out double x) ||
                !body.TryGetDouble("y", out double y) ||
                !body.TryGetDouble("imageWidth", out double imageWidth) ||
                !body.TryGetDouble("imageHeight", out double imageHeight))
            {
                return BridgeResponse.Failure(
                    "invalid_argument",
                    "body 必须包含数值字段 x、y、imageWidth、imageHeight");
            }

            if (!IsFiniteFloat(x) ||
                !IsFiniteFloat(y) ||
                !IsFiniteFloat(imageWidth) ||
                !IsFiniteFloat(imageHeight))
            {
                return BridgeResponse.Failure(
                    "invalid_argument",
                    "x/y/imageWidth/imageHeight 必须是 float 范围内的有限数值");
            }

            if (imageWidth <= 0 || imageHeight <= 0)
            {
                return BridgeResponse.Failure("invalid_argument", "imageWidth/imageHeight 必须为正数");
            }

            if (!EditorApplication.isPlaying)
            {
                return BridgeResponse.Failure("not_in_play_mode", "hit-test 需要 Play Mode");
            }

            Vector2 screenPoint = ScreenshotAnnotationRenderer.ImageToUnityScreen(
                (float)x,
                (float)y,
                (float)imageWidth,
                (float)imageHeight,
                Screen.width,
                Screen.height);

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["coordinateSpace"] = "unity-screen-bottom-left";
            JsonValue screen = JsonValue.NewObject();
            screen["x"] = screenPoint.x;
            screen["y"] = screenPoint.y;
            screen["width"] = Screen.width;
            screen["height"] = Screen.height;
            response["screen"] = screen;

            JsonValue ugui = JsonValue.NewObject();
            IUiHitTestBackend hitBackend = null;
            bool uguiAvailable = services != null && services.TryGet(out hitBackend);
            ugui["available"] = uguiAvailable;
            JsonValue uguiHits = JsonValue.NewArray();
            if (uguiAvailable && hitBackend != null)
            {
                foreach (UiHitResult hit in hitBackend.Raycast(screenPoint))
                {
                    JsonValue item = JsonValue.NewObject();
                    item["path"] = hit.Path ?? string.Empty;
                    item["name"] = hit.Name ?? string.Empty;
                    item["depth"] = hit.Depth;
                    item["module"] = hit.Module ?? string.Empty;
                    item["sortingOrder"] = hit.SortingOrder;
                    item["distance"] = hit.Distance;
                    uguiHits.Add(item);
                }
            }

            ugui["hits"] = uguiHits;
            response["ugui"] = ugui;

            JsonValue physics = Physics3DHitTester.BuildHitsJson(screenPoint);
            response["physics3d"] = physics;
            return response;
        }

        private static bool IsFiniteFloat(double value)
        {
            return !double.IsNaN(value) &&
                   !double.IsInfinity(value) &&
                   value >= -float.MaxValue &&
                   value <= float.MaxValue;
        }
    }

    /// <summary>Physics 3D 命中：Camera.main → 首个 enabled 且 targetDisplay=0 的 Camera。</summary>
    internal static class Physics3DHitTester
    {
        internal static JsonValue BuildHitsJson(Vector2 screenPoint)
        {
            JsonValue root = JsonValue.NewObject();
            Camera camera = ResolveCamera();
            root["cameraAvailable"] = camera != null;
            JsonValue hits = JsonValue.NewArray();
            if (camera == null)
            {
                root["hits"] = hits;
                root["cameraName"] = JsonValue.Null;
                return root;
            }

            root["cameraName"] = camera.name;
            Ray ray = camera.ScreenPointToRay(new Vector3(screenPoint.x, screenPoint.y, 0f));
            RaycastHit[] rawHits = Physics.RaycastAll(ray);
            Array.Sort(rawHits, (a, b) => a.distance.CompareTo(b.distance));

            foreach (RaycastHit hit in rawHits)
            {
                if (hit.collider == null)
                {
                    continue;
                }

                Transform transform = hit.collider.transform;
                JsonValue item = JsonValue.NewObject();
                item["path"] = NodePath.BuildPath(transform);
                item["name"] = transform.name;
                item["layer"] = LayerMask.LayerToName(hit.collider.gameObject.layer);
                item["layerNumber"] = hit.collider.gameObject.layer;
                item["distance"] = hit.distance;
                JsonValue point = JsonValue.NewObject();
                point["x"] = hit.point.x;
                point["y"] = hit.point.y;
                point["z"] = hit.point.z;
                item["point"] = point;
                JsonValue normal = JsonValue.NewObject();
                normal["x"] = hit.normal.x;
                normal["y"] = hit.normal.y;
                normal["z"] = hit.normal.z;
                item["normal"] = normal;
                hits.Add(item);
            }

            root["hits"] = hits;
            return root;
        }

        internal static Camera ResolveCamera()
        {
            return ResolveCamera(Camera.main, UnityEngine.Object.FindObjectsOfType<Camera>());
        }

        internal static Camera ResolveCamera(Camera main, IReadOnlyList<Camera> cameras)
        {
            if (main != null && main.enabled)
            {
                return main;
            }

            if (cameras == null)
            {
                return null;
            }

            foreach (Camera camera in cameras)
            {
                if (camera == null || !camera.enabled)
                {
                    continue;
                }

                if (camera.targetDisplay == 0)
                {
                    return camera;
                }
            }

            return null;
        }
    }
}
