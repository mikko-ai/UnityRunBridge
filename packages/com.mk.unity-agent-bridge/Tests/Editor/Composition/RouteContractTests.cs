using System.Collections.Generic;
using System.Linq;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Contract
{
    /// <summary>
    /// 冻结完整安装下的 HTTP 路由顺序与 capability 数组。重构后必须保持
    /// method/path 顺序、capability ordinal 排序和 NoUGUI 删除规则不变。
    /// </summary>
    public sealed class RouteContractTests
    {
        // Features Module Order + Host 追加 GET /capabilities 的冻结顺序。
        private static readonly (string Method, string Path)[] FullInstallRoutes =
        {
            ("GET", "status"),
            ("POST", "refresh"),
            ("POST", "play"),
            ("POST", "stop"),
            ("POST", "pause"),
            ("POST", "resume"),
            ("POST", "open-scene"),
            ("POST", "session/start"),
            ("POST", "session/end"),
            ("GET", "session/status"),
            ("GET", "jobs/{id}"),
            ("GET", "hierarchy/roots"),
            ("GET", "hierarchy/tree"),
            ("GET", "hierarchy/find"),
            ("GET", "hierarchy/ancestors"),
            ("GET", "hierarchy/inspect"),
            ("POST", "capture/screenshot"),
            ("POST", "interaction/click"),
            ("POST", "interaction/input"),
            ("POST", "interaction/set-value"),
            ("GET", "gameplay/commands"),
            ("POST", "gameplay/invoke"),
            ("POST", "recording/start"),
            ("POST", "recording/stop"),
            ("GET", "recording/status"),
            ("POST", "profiling/start"),
            ("POST", "profiling/stop"),
            ("GET", "profiling/status"),
            ("POST", "health/scan-prefabs"),
            ("GET", "capabilities"),
        };

        // CapabilityRegistry.All() 使用 ordinal 排序。
        private static readonly string[] FullInstallCapabilities =
        {
            "capture",
            "core",
            "gameplay",
            "health",
            "hierarchy",
            "interaction",
            "jobs",
            "profiling",
            "recording",
        };

        private static readonly string[] NoUguiCapabilities =
        {
            "capture",
            "core",
            "gameplay",
            "health",
            "hierarchy",
            "jobs",
            "profiling",
        };

        private static bool HasUguiCapabilities()
        {
            IReadOnlyList<string> caps = CapabilityRegistry.All();
            return caps.Contains("interaction") && caps.Contains("recording");
        }

        private static List<(string Method, string Path)> BuildNoUguiRoutes()
        {
            List<(string Method, string Path)> expected = new List<(string, string)>();
            foreach ((string method, string path) in FullInstallRoutes)
            {
                if (path.StartsWith("interaction/") || path.StartsWith("recording/"))
                {
                    continue;
                }

                expected.Add((method, path));
            }

            return expected;
        }

        [Test]
        public void FullInstall_RegistersExactlyThirtyRoutesInOrder()
        {
            if (!HasUguiCapabilities())
            {
                Assert.Ignore("完整安装契约仅在 UGUI Adapter 可用时运行");
            }

            IReadOnlyList<(string Method, string Path)> actual = RouteTable.ListRoutes();

            Assert.AreEqual(FullInstallRoutes.Length, actual.Count, "完整安装路由数应为 30");
            for (int i = 0; i < FullInstallRoutes.Length; i++)
            {
                Assert.AreEqual(FullInstallRoutes[i].Method, actual[i].Method, $"route[{i}].method");
                Assert.AreEqual(FullInstallRoutes[i].Path, actual[i].Path, $"route[{i}].path");
            }
        }

        [Test]
        public void FullInstall_CapabilitiesAreExactlyNineInOrdinalOrder()
        {
            if (!HasUguiCapabilities())
            {
                Assert.Ignore("完整安装契约仅在 UGUI Adapter 可用时运行");
            }

            IReadOnlyList<string> actual = CapabilityRegistry.All();

            Assert.AreEqual(FullInstallCapabilities.Length, actual.Count, "完整安装 capability 数应为 9");
            for (int i = 0; i < FullInstallCapabilities.Length; i++)
            {
                Assert.AreEqual(FullInstallCapabilities[i], actual[i], $"capability[{i}]");
            }
        }

        [Test]
        public void CapabilitiesResponse_MatchesRouteAndCapabilitySnapshots()
        {
            if (!HasUguiCapabilities())
            {
                Assert.Ignore("完整安装契约仅在 UGUI Adapter 可用时运行");
            }

            // Composition 测试只走 public Core 门面，不依赖 Features.CapabilitiesController internals。
            JsonValue response = CapabilitiesResponseBuilder.Build(
                CapabilityRegistry.All(),
                RouteTable.ListRoutes());

            Assert.IsTrue(response["ok"].AsBoolean);
            Assert.AreEqual(BridgeConfig.Version, response["bridgeVersion"].AsString);

            List<string> capabilities = new List<string>();
            foreach (JsonValue item in response["capabilities"].Items)
            {
                capabilities.Add(item.AsString);
            }

            CollectionAssert.AreEqual(FullInstallCapabilities, capabilities);

            List<(string Method, string Path)> routes = new List<(string, string)>();
            foreach (JsonValue item in response["routes"].Items)
            {
                routes.Add((item["method"].AsString, item["path"].AsString));
            }

            Assert.AreEqual(FullInstallRoutes.Length, routes.Count);
            for (int i = 0; i < FullInstallRoutes.Length; i++)
            {
                Assert.AreEqual(FullInstallRoutes[i].Method, routes[i].Method, $"response.routes[{i}].method");
                Assert.AreEqual(FullInstallRoutes[i].Path, routes[i].Path, $"response.routes[{i}].path");
            }
        }

        [Test]
        public void NoUgui_ExpectedRouteOrder_IsFullInstallWithoutInteractionAndRecording()
        {
            List<(string Method, string Path)> expected = BuildNoUguiRoutes();

            Assert.AreEqual(24, expected.Count, "NoUGUI 路由数应为 24");
            Assert.AreEqual(("GET", "status"), expected[0]);
            Assert.AreEqual(("GET", "jobs/{id}"), expected[10]);
            Assert.AreEqual(("POST", "capture/screenshot"), expected[16]);
            Assert.AreEqual(("GET", "gameplay/commands"), expected[17]);
            Assert.AreEqual(("POST", "health/scan-prefabs"), expected[22]);
            Assert.AreEqual(("GET", "capabilities"), expected[23]);
        }

        [Test]
        public void NoUgui_ExpectedCapabilities_AreSevenWithoutInteractionAndRecording()
        {
            Assert.AreEqual(7, NoUguiCapabilities.Length);
            CollectionAssert.DoesNotContain(NoUguiCapabilities, "interaction");
            CollectionAssert.DoesNotContain(NoUguiCapabilities, "recording");
            CollectionAssert.Contains(NoUguiCapabilities, "hierarchy");
            CollectionAssert.Contains(NoUguiCapabilities, "jobs");
        }

        [Test]
        public void NoUgui_RuntimeRegistersExactlyTwentyFourRoutesInOrder()
        {
            if (HasUguiCapabilities())
            {
                Assert.Ignore("NoUGUI 运行时契约仅在无 UGUI Adapter 时运行");
            }

            List<(string Method, string Path)> expected = BuildNoUguiRoutes();
            IReadOnlyList<(string Method, string Path)> actual = RouteTable.ListRoutes();

            Assert.AreEqual(expected.Count, actual.Count, "NoUGUI 路由数应为 24");
            for (int i = 0; i < expected.Count; i++)
            {
                Assert.AreEqual(expected[i].Method, actual[i].Method, $"route[{i}].method");
                Assert.AreEqual(expected[i].Path, actual[i].Path, $"route[{i}].path");
            }
        }

        [Test]
        public void NoUgui_RuntimeCapabilitiesAreExactlySevenInOrdinalOrder()
        {
            if (HasUguiCapabilities())
            {
                Assert.Ignore("NoUGUI 运行时契约仅在无 UGUI Adapter 时运行");
            }

            IReadOnlyList<string> actual = CapabilityRegistry.All();

            Assert.AreEqual(NoUguiCapabilities.Length, actual.Count, "NoUGUI capability 数应为 7");
            for (int i = 0; i < NoUguiCapabilities.Length; i++)
            {
                Assert.AreEqual(NoUguiCapabilities[i], actual[i], $"capability[{i}]");
            }

            CollectionAssert.DoesNotContain(actual.ToList(), "interaction");
            CollectionAssert.DoesNotContain(actual.ToList(), "recording");
        }

        [Test]
        public void NoUgui_UguiAdapterAssemblyIsNotCompiled()
        {
            if (HasUguiCapabilities())
            {
                Assert.Ignore("NoUGUI 程序集守卫仅在无 UGUI Adapter 时运行");
            }

            bool uguiAdapterPresent = false;
            bool uguiAdapterTestsPresent = false;
            foreach (UnityEditor.Compilation.Assembly assembly in UnityEditor.Compilation.CompilationPipeline.GetAssemblies())
            {
                if (assembly.name == "Mk.UnityAgentBridge.Editor.Adapters.UGUI")
                {
                    uguiAdapterPresent = true;
                }

                if (assembly.name == "Mk.UnityAgentBridge.Editor.Adapters.UGUI.Tests"
                    || assembly.name == "Mk.UnityAgentBridge.Editor.Tests.UGUI"
                    || assembly.name == "Mk.UnityAgentBridge.Editor.Tests.UGUI.EditorIntegration")
                {
                    uguiAdapterTestsPresent = true;
                }
            }

            Assert.IsFalse(uguiAdapterPresent, "NoUGUI 下 UGUI Adapter 程序集不应参与编译");
            Assert.IsFalse(uguiAdapterTestsPresent, "NoUGUI 下 UGUI 相关测试程序集不应参与编译");
        }
    }
}
