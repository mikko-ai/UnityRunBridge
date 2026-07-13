using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEditor.PackageManager;

namespace Mk.UnityAgentBridge.Editor.Tests.Routing
{
    public sealed class CapabilitiesControllerTests
    {
        private static bool HasUguiCapabilities()
        {
            foreach (string capability in CapabilityRegistry.All())
            {
                if (capability == "interaction")
                {
                    return true;
                }
            }

            return false;
        }

        [Test]
        public void BuildResponse_IncludesBridgeVersionAndCoreCapability()
        {
            JsonValue response = CapabilitiesController.BuildResponse();

            Assert.IsTrue(response["ok"].AsBoolean);
            Assert.AreEqual(BridgeConfig.Version, response["bridgeVersion"].AsString);

            bool hasCore = false;
            foreach (JsonValue capability in response["capabilities"].Items)
            {
                if (capability.AsString == "core")
                {
                    hasCore = true;
                }
            }

            Assert.IsTrue(hasCore);
        }

        [Test]
        public void BuildResponse_ListsRegisteredRoutes()
        {
            JsonValue response = CapabilitiesController.BuildResponse();
            if (HasUguiCapabilities())
            {
                Assert.AreEqual(30, response["routes"].Count, "完整安装应暴露 30 条路由");
                Assert.AreEqual(9, response["capabilities"].Count, "完整安装应暴露 9 个 capability");
            }
            else
            {
                Assert.AreEqual(24, response["routes"].Count, "NoUGUI 应暴露 24 条路由");
                Assert.AreEqual(7, response["capabilities"].Count, "NoUGUI 应暴露 7 个 capability");
            }
        }

        [Test]
        public void BridgeVersion_MatchesPackageJsonVersion()
        {
            PackageInfo packageInfo = PackageInfo.FindForAssembly(typeof(BridgeConfig).Assembly);
            Assert.IsNotNull(packageInfo, "无法通过 PackageInfo 找到本包，检查测试工程的包依赖是否为 file: 引用");
            Assert.AreEqual(packageInfo.version, BridgeConfig.Version);
        }
    }
}
