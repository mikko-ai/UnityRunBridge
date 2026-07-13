using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Host
{
    /// <summary>
    /// 实例服务注册表：优先级降序 + 类型全名升序；TryGet 命中并列最高优先级视为单选冲突。
    /// </summary>
    public sealed class BridgeServiceRegistryTests
    {
        [Test]
        public void GetAll_SortsByPriorityDescendingThenTypeName()
        {
            BridgeServiceRegistry registry = new BridgeServiceRegistry();
            FakeServiceA low = new FakeServiceA();
            FakeServiceB high = new FakeServiceB();
            registry.Add<IFakeService>(low, 5);
            registry.Add<IFakeService>(high, 10);

            System.Collections.Generic.IReadOnlyList<IFakeService> all = registry.GetAll<IFakeService>();

            Assert.AreEqual(2, all.Count);
            Assert.AreSame(high, all[0]);
            Assert.AreSame(low, all[1]);
        }

        [Test]
        public void GetAll_SamePriority_OrdersByTypeNameAscending()
        {
            BridgeServiceRegistry registry = new BridgeServiceRegistry();
            FakeServiceB b = new FakeServiceB();
            FakeServiceA a = new FakeServiceA();
            registry.Add<IFakeService>(b, 5);
            registry.Add<IFakeService>(a, 5);

            System.Collections.Generic.IReadOnlyList<IFakeService> all = registry.GetAll<IFakeService>();

            Assert.AreSame(a, all[0], "FakeServiceA 的全名应排在 FakeServiceB 前");
            Assert.AreSame(b, all[1]);
        }

        [Test]
        public void TryGet_SingleImplementation_ReturnsIt()
        {
            BridgeServiceRegistry registry = new BridgeServiceRegistry();
            FakeServiceA a = new FakeServiceA();
            registry.Add<IFakeService>(a, 1);

            Assert.IsTrue(registry.TryGet(out IFakeService resolved));
            Assert.AreSame(a, resolved);
        }

        [Test]
        public void TryGet_NoImplementation_ReturnsFalse()
        {
            BridgeServiceRegistry registry = new BridgeServiceRegistry();
            Assert.IsFalse(registry.TryGet(out IFakeService resolved));
            Assert.IsNull(resolved);
        }

        [Test]
        public void TryGet_DistinctPriorities_ReturnsHighest()
        {
            BridgeServiceRegistry registry = new BridgeServiceRegistry();
            FakeServiceA low = new FakeServiceA();
            FakeServiceB high = new FakeServiceB();
            registry.Add<IFakeService>(low, 5);
            registry.Add<IFakeService>(high, 20);

            Assert.IsTrue(registry.TryGet(out IFakeService resolved));
            Assert.AreSame(high, resolved);
        }

        [Test]
        public void TryGet_TiedTopPriority_ThrowsConflict()
        {
            BridgeServiceRegistry registry = new BridgeServiceRegistry();
            registry.Add<IFakeService>(new FakeServiceA(), 5);
            registry.Add<IFakeService>(new FakeServiceB(), 5);

            Assert.Throws<BridgeServiceConflictException>(() => registry.TryGet(out IFakeService _));
        }
    }
}
