using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEditor.PackageManager;

namespace Mk.UnityAgentBridge.Editor.Tests.Routing
{
    public sealed class CapabilitiesControllerTests
    {
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
            Assert.Greater(response["routes"].Count, 0);
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
