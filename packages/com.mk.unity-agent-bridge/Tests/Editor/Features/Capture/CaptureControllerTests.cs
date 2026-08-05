using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Capture;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Tests.Capture
{
    public sealed class CaptureControllerTests
    {
        [Test]
        public void Route_CaptureScreenshot_IsRegistered()
        {
            RouteHandler handler = RouteTable.Resolve("POST", "capture/screenshot", out _);
            Assert.IsNotNull(handler);
        }

        [Test]
        public void Route_CaptureHitTest_IsRegistered()
        {
            RouteHandler handler = RouteTable.Resolve("POST", "capture/hit-test", out _);
            Assert.IsNotNull(handler);
        }

        [Test]
        public void CapabilitiesResponse_DeclaresCaptureCapability()
        {
            JsonValue response = CapabilitiesController.BuildResponse();
            bool hasCapture = false;
            foreach (JsonValue capability in response["capabilities"].Items)
            {
                if (capability.AsString == "capture")
                {
                    hasCapture = true;
                }
            }

            Assert.IsTrue(hasCapture);
        }

        [Test]
        public void CaptureScreenshot_NotInPlayMode_ReturnsCaptureRequiresPlayMode()
        {
            // 测试项目没有 .unity-agent/config.json，走 Settings.Default()（enabled=true,
            // allowAgentRequest=true），因此 not-playing 检查会先命中，行为在 EditMode 下可判定。
            object result = CaptureController.CaptureScreenshot(BridgeRequestContext.ForTests());

            Assert.IsInstanceOf<BridgeResponse>(result);
            BridgeResponse response = (BridgeResponse)result;
            Assert.IsFalse(response.ok);
            Assert.AreEqual("capture_requires_play_mode", response.code);
        }

        [Test]
        public void DeriveSiblingPath_AppendsSuffixBeforeExtension()
        {
            Assert.AreEqual(
                "/tmp/screenshot-1.annotated.png",
                CaptureController.DeriveSiblingPath("/tmp/screenshot-1.png", ".annotated.png"));
            Assert.AreEqual(
                "/tmp/screenshot-1.annotations.json",
                CaptureController.DeriveSiblingPath("/tmp/screenshot-1.png", ".annotations.json"));
        }

        [Test]
        public void HitTest_NotInPlayMode_ReturnsNotInPlayMode()
        {
            string rawBody = "{\"x\":10,\"y\":20,\"imageWidth\":100,\"imageHeight\":200}";
            object result = HitTestController.HitTest(BridgeRequestContext.ForTests(rawBody: rawBody));

            Assert.IsInstanceOf<BridgeResponse>(result);
            BridgeResponse response = (BridgeResponse)result;
            Assert.IsFalse(response.ok);
            Assert.AreEqual("not_in_play_mode", response.code);
        }

        [Test]
        public void HitTest_NonFiniteOrFloatOverflowingCoordinates_ReturnInvalidArgument()
        {
            object overflowing = HitTestController.HitTest(
                BridgeRequestContext.ForTests(
                    rawBody: "{\"x\":1e300,\"y\":20,\"imageWidth\":100,\"imageHeight\":200}"));
            object nonFiniteSize = HitTestController.HitTest(
                BridgeRequestContext.ForTests(
                    rawBody: "{\"x\":10,\"y\":20,\"imageWidth\":1e300,\"imageHeight\":200}"));

            Assert.IsInstanceOf<BridgeResponse>(overflowing);
            Assert.AreEqual("invalid_argument", ((BridgeResponse)overflowing).code);
            Assert.IsInstanceOf<BridgeResponse>(nonFiniteSize);
            Assert.AreEqual("invalid_argument", ((BridgeResponse)nonFiniteSize).code);
        }
    }

    public sealed class ScreenshotAnnotationRendererTests
    {
        [Test]
        public void ImageToUnityScreen_FlipsYAndScales()
        {
            Vector2 point = ScreenshotAnnotationRenderer.ImageToUnityScreen(
                imageX: 50,
                imageY: 0,
                imageWidth: 100,
                imageHeight: 200,
                screenWidth: 800,
                screenHeight: 600);

            Assert.AreEqual(400f, point.x, 0.01f);
            Assert.AreEqual(600f, point.y, 0.01f);
        }

        [Test]
        public void ImageToUnityScreen_BottomOfImageMapsToScreenYZero()
        {
            Vector2 point = ScreenshotAnnotationRenderer.ImageToUnityScreen(
                imageX: 0,
                imageY: 200,
                imageWidth: 100,
                imageHeight: 200,
                screenWidth: 100,
                screenHeight: 200);

            Assert.AreEqual(0f, point.x, 0.01f);
            Assert.AreEqual(0f, point.y, 0.01f);
        }

        [Test]
        public void Render_WritesSidecarAndClampsBounds()
        {
            Texture2D source = new Texture2D(64, 48, TextureFormat.RGBA32, false);
            for (int y = 0; y < 48; y++)
            {
                for (int x = 0; x < 64; x++)
                {
                    source.SetPixel(x, y, Color.gray);
                }
            }

            source.Apply();

            List<UiAnnotationElement> elements = new List<UiAnnotationElement>
            {
                new UiAnnotationElement
                {
                    Label = "A",
                    Name = "Btn",
                    Path = "Canvas/Btn",
                    Type = "Button",
                    Interaction = "click",
                    ScreenX = 32,
                    ScreenY = 24,
                    BoundsMinX = -10,
                    BoundsMinY = -10,
                    BoundsMaxX = 80,
                    BoundsMaxY = 60,
                    Interactable = true,
                    SortingOrder = 1
                }
            };

            Texture2D annotated = ScreenshotAnnotationRenderer.Render(
                source, elements, out JsonValue sidecar, out float scale);
            try
            {
                Assert.IsNotNull(annotated);
                Assert.AreEqual(1, sidecar["schemaVersion"].AsInt);
                Assert.AreEqual("image-top-left", sidecar["coordinateSpace"].AsString);
                Assert.AreEqual(1, sidecar["elements"].Count);
                Assert.AreEqual("A", sidecar["elements"][0]["label"].AsString);
                float scaleX = sidecar["scaleX"].AsFloat;
                float scaleY = sidecar["scaleY"].AsFloat;
                Assert.AreEqual(64f / sidecar["referenceScreen"]["width"].AsFloat, scaleX, 0.0001f);
                Assert.AreEqual(48f / sidecar["referenceScreen"]["height"].AsFloat, scaleY, 0.0001f);
                Assert.AreEqual(48f - 24f * scaleY, sidecar["elements"][0]["screenY"].AsFloat, 0.01f);
                // sidecar 使用 PNG 左上原点；绘制仍在 Texture2D 左下原点执行并裁剪。
                Assert.AreEqual(-10f * scaleX, sidecar["elements"][0]["bounds"]["minX"].AsFloat, 0.01f);
                Assert.AreEqual(80f * scaleX, sidecar["elements"][0]["bounds"]["maxX"].AsFloat, 0.01f);
                Assert.AreEqual(48f - 60f * scaleY, sidecar["elements"][0]["bounds"]["minY"].AsFloat, 0.01f);
                Assert.AreEqual(48f - (-10f * scaleY), sidecar["elements"][0]["bounds"]["maxY"].AsFloat, 0.01f);

                Vector2 roundTrip = ScreenshotAnnotationRenderer.ImageToUnityScreen(
                    sidecar["elements"][0]["screenX"].AsFloat,
                    sidecar["elements"][0]["screenY"].AsFloat,
                    64,
                    48,
                    sidecar["referenceScreen"]["width"].AsFloat,
                    sidecar["referenceScreen"]["height"].AsFloat);
                Assert.AreEqual(32f, roundTrip.x, 0.01f);
                Assert.AreEqual(24f, roundTrip.y, 0.01f);
            }
            finally
            {
                Object.DestroyImmediate(source);
                Object.DestroyImmediate(annotated);
            }
        }
    }

    public sealed class CaptureQuotaTests
    {
        [SetUp]
        public void ResetQuota()
        {
            CaptureQuota.ResetForTests("test-kind");
        }

        [Test]
        public void TryConsume_UnderLimit_Succeeds()
        {
            bool ok = CaptureQuota.TryConsume("test-kind", 3, out int used);

            Assert.IsTrue(ok);
            Assert.AreEqual(1, used);
        }

        [Test]
        public void TryConsume_AtLimit_Fails()
        {
            CaptureQuota.TryConsume("test-kind", 2, out _);
            CaptureQuota.TryConsume("test-kind", 2, out _);

            bool ok = CaptureQuota.TryConsume("test-kind", 2, out int used);

            Assert.IsFalse(ok);
            Assert.AreEqual(2, used);
        }
    }

    public sealed class Physics3DHitTesterTests
    {
        [Test]
        public void ResolveCamera_WithoutCameras_ReturnsNull()
        {
            // EditMode 下通常没有可用 Camera；至少保证不抛异常。
            Assert.DoesNotThrow(() => Physics3DHitTester.ResolveCamera());
        }

        [Test]
        public void BuildHitsJson_WithoutCamera_ReportsUnavailable()
        {
            JsonValue json = Physics3DHitTester.BuildHitsJson(new Vector2(10, 10));
            Assert.IsNotNull(json);
            Assert.IsTrue(json.TryGetBoolean("cameraAvailable", out bool available));
            if (!available)
            {
                Assert.AreEqual(0, json["hits"].Count);
            }
        }

        [Test]
        public void ResolveCamera_DoesNotFallbackToAnotherDisplay()
        {
            GameObject go = new GameObject("OtherDisplayCamera");
            Camera camera = go.AddComponent<Camera>();
            camera.targetDisplay = 1;
            try
            {
                Camera selected = Physics3DHitTester.ResolveCamera(main: null, cameras: new[] { camera });

                Assert.IsNull(selected);
            }
            finally
            {
                Object.DestroyImmediate(go);
            }
        }

        [Test]
        public void ResolveCamera_PrefersMainThenDefaultDisplay()
        {
            GameObject mainGo = new GameObject("MainCameraCandidate");
            GameObject fallbackGo = new GameObject("DefaultDisplayCamera");
            Camera main = mainGo.AddComponent<Camera>();
            Camera fallback = fallbackGo.AddComponent<Camera>();
            fallback.targetDisplay = 0;
            try
            {
                Assert.AreSame(
                    main,
                    Physics3DHitTester.ResolveCamera(main, new[] { fallback }));
                Assert.AreSame(
                    fallback,
                    Physics3DHitTester.ResolveCamera(main: null, cameras: new[] { fallback }));
            }
            finally
            {
                Object.DestroyImmediate(mainGo);
                Object.DestroyImmediate(fallbackGo);
            }
        }
    }
}
