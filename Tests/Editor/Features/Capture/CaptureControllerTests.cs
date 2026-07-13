using Mk.UnityAgentBridge.Editor.Capture;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;

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
}
