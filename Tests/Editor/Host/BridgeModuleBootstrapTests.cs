using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Host;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Host
{
    /// <summary>
    /// 事务装配核心行为：注入 Fake 候选（不污染生产 TypeCache），覆盖顺序、可用性过滤、
    /// 重复路由 / 重复 capability / 单选冲突 / 构造异常回滚、生命周期去重与逆序回滚、
    /// 以及生产 Discover 不采集无 assembly marker 的测试 Fake。
    /// </summary>
    public sealed class BridgeModuleBootstrapTests
    {
        private static readonly Type[] NoAdapters = new Type[0];

        [Test]
        public void ComposeSnapshot_RegistersRoutesInModuleOrder_AndSortsCapabilities()
        {
            BridgeComposition composition = BridgeModuleBootstrap.ComposeSnapshot(
                NoAdapters,
                new[] { typeof(ModuleOrder20), typeof(ModuleOrder10) });

            IReadOnlyList<(string Method, string Path)> routes = composition.Runtime.Routes.ListRoutes();
            Assert.AreEqual(2, routes.Count);
            Assert.AreEqual("r/10", routes[0].Path, "Order 较小的模块路由应在前");
            Assert.AreEqual("r/20", routes[1].Path);

            IReadOnlyList<string> capabilities = composition.Runtime.Capabilities.All();
            CollectionAssert.AreEqual(new[] { "cap10", "cap20" }, capabilities);
        }

        [Test]
        public void ComposeSnapshot_SkipsUnavailableModules()
        {
            BridgeComposition composition = BridgeModuleBootstrap.ComposeSnapshot(
                NoAdapters,
                new[] { typeof(UnavailableModule), typeof(ModuleOrder10) });

            IReadOnlyList<(string Method, string Path)> routes = composition.Runtime.Routes.ListRoutes();
            Assert.AreEqual(1, routes.Count);
            Assert.AreEqual("r/10", routes[0].Path);
            CollectionAssert.AreEqual(new[] { "cap10" }, composition.Runtime.Capabilities.All());
        }

        [Test]
        public void ComposeSnapshot_DuplicateRoute_ThrowsCompositionException()
        {
            Assert.Throws<BridgeCompositionException>(() =>
                BridgeModuleBootstrap.ComposeSnapshot(
                    NoAdapters,
                    new[] { typeof(DupRouteModuleA), typeof(DupRouteModuleB) }));
        }

        [Test]
        public void ComposeSnapshot_DuplicateCapability_ThrowsCompositionException()
        {
            Assert.Throws<BridgeCompositionException>(() =>
                BridgeModuleBootstrap.ComposeSnapshot(
                    NoAdapters,
                    new[] { typeof(DupCapModuleA), typeof(DupCapModuleB) }));
        }

        [Test]
        public void ComposeSnapshot_ConstructorThrows_ThrowsCompositionException()
        {
            Assert.Throws<BridgeCompositionException>(() =>
                BridgeModuleBootstrap.ComposeSnapshot(
                    NoAdapters,
                    new[] { typeof(ThrowingCtorModule) }));
        }

        [Test]
        public void ComposeSnapshot_ServiceSingleSelectConflict_ThrowsCompositionException()
        {
            Assert.Throws<BridgeCompositionException>(() =>
                BridgeModuleBootstrap.ComposeSnapshot(
                    new[] { typeof(FakeConflictAdapter) },
                    new[] { typeof(ServiceProbingModule) }));
        }

        [Test]
        public void ComposeSnapshot_CollectsLifecycleModuleOnce()
        {
            BridgeComposition composition = BridgeModuleBootstrap.ComposeSnapshot(
                NoAdapters,
                new[] { typeof(LifecycleModule) });

            Assert.AreEqual(1, composition.Lifecycles.Count);
            Assert.IsInstanceOf<LifecycleModule>(composition.Lifecycles[0]);
            Assert.AreEqual(1, composition.Candidates.Count);
        }

        [Test]
        public void StartLifecycles_ReverseStopsAlreadyStartedOnFailure()
        {
            List<string> log = new List<string>();
            RecordingLifecycle a = new RecordingLifecycle("A", log);
            RecordingLifecycle b = new RecordingLifecycle("B", log);
            RecordingLifecycle failing = new RecordingLifecycle("F", log, throwOnStart: true);

            Assert.Throws<InvalidOperationException>(() =>
                BridgeModuleBootstrap.StartLifecycles(new IBridgeLifecycle[] { a, b, failing }));

            CollectionAssert.AreEqual(
                new[] { "start:A", "start:B", "start:F", "stop:B", "stop:A" },
                log);
        }

        [Test]
        public void DiscoverProductionCandidates_ExcludesTestFakeWithoutAssemblyMarker()
        {
            BridgeModuleBootstrap.DiscoverProductionCandidates(out _, out List<Type> moduleTypes);

            CollectionAssert.DoesNotContain(moduleTypes, typeof(PoisonModule),
                "测试程序集无 [BridgeDiscoveryAssembly]，其 [BridgeModule] Fake 不得被生产 Discover 采集");
            Assert.IsTrue(
                moduleTypes.Exists(t => t.Name == "CoreBridgeModule"),
                "Features 带 assembly marker，其 CoreBridgeModule 应被 Discover 采集");
        }
    }
}
