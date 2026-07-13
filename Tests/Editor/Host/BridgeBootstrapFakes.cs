using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;

namespace Mk.UnityAgentBridge.Editor.Tests.Host
{
    // 仅供 Host.Tests 注入 ComposeSnapshot 的 Fake 候选。它们不带 assembly 级 [BridgeDiscoveryAssembly]，
    // 因此不会被生产 Discover 采集（PoisonModule 专门用来验证这一点）。ComposeSnapshot 通过 Activator
    // 构造它们，故均为 public 且带 public 无参构造。

    public interface IFakeService
    {
    }

    public sealed class FakeServiceA : IFakeService
    {
    }

    public sealed class FakeServiceB : IFakeService
    {
    }

    /// <summary>注册两个同优先级 IFakeService，制造单选冲突场景。</summary>
    public sealed class FakeConflictAdapter : IBridgeAdapter
    {
        public int Priority => 100;

        public void RegisterServices(IBridgeServiceRegistry services)
        {
            services.Add<IFakeService>(new FakeServiceA(), 5);
            services.Add<IFakeService>(new FakeServiceB(), 5);
        }
    }

    public sealed class ModuleOrder10 : IBridgeModule
    {
        public string Capability => "cap10";
        public int Order => 10;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "r/10", _ => "10");
        }
    }

    public sealed class ModuleOrder20 : IBridgeModule
    {
        public string Capability => "cap20";
        public int Order => 20;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "r/20", _ => "20");
        }
    }

    public sealed class UnavailableModule : IBridgeModule
    {
        public string Capability => "unavail";
        public int Order => 30;
        public bool IsAvailable(IBridgeServiceResolver services) => false;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "unavail/x", _ => "x");
        }
    }

    public sealed class DupRouteModuleA : IBridgeModule
    {
        public string Capability => "dupRouteA";
        public int Order => 10;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "dup/x", _ => "a");
        }
    }

    public sealed class DupRouteModuleB : IBridgeModule
    {
        public string Capability => "dupRouteB";
        public int Order => 20;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "dup/x", _ => "b");
        }
    }

    public sealed class DupCapModuleA : IBridgeModule
    {
        public string Capability => "dupcap";
        public int Order => 10;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "cap/a", _ => "a");
        }
    }

    public sealed class DupCapModuleB : IBridgeModule
    {
        public string Capability => "dupcap";
        public int Order => 20;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "cap/b", _ => "b");
        }
    }

    public sealed class ThrowingCtorModule : IBridgeModule
    {
        public ThrowingCtorModule()
        {
            throw new InvalidOperationException("boom in ctor");
        }

        public string Capability => "throwing";
        public int Order => 10;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
        }
    }

    /// <summary>IsAvailable 触发服务单选解析；配合 FakeConflictAdapter 制造冲突。</summary>
    public sealed class ServiceProbingModule : IBridgeModule
    {
        public string Capability => "probe";
        public int Order => 40;

        public bool IsAvailable(IBridgeServiceResolver services)
        {
            return services.TryGet<IFakeService>(out _);
        }

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "probe/x", _ => "x");
        }
    }

    /// <summary>同时是 Module 与 Lifecycle，用于验证生命周期按引用去重（只收一次）。</summary>
    public sealed class LifecycleModule : IBridgeModule, IBridgeLifecycle
    {
        public string Capability => "lifecycle";
        public int Order => 10;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "lifecycle/x", _ => "x");
        }

        public void Start()
        {
        }

        public void Stop()
        {
        }

        public void Dispose()
        {
        }
    }

    /// <summary>带 [BridgeModule] 但位于无 [BridgeDiscoveryAssembly] 标记的测试程序集，用于验证生产 Discover 不采集测试 Fake。</summary>
    [BridgeModule]
    public sealed class PoisonModule : IBridgeModule
    {
        public string Capability => "poison";
        public int Order => 999;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
        }
    }

    /// <summary>记录 Start/Stop 调用顺序的生命周期 Fake，用于验证逆序回滚。</summary>
    public sealed class RecordingLifecycle : IBridgeLifecycle
    {
        private readonly string name;
        private readonly List<string> log;
        private readonly bool throwOnStart;

        public RecordingLifecycle(string name, List<string> log, bool throwOnStart = false)
        {
            this.name = name;
            this.log = log;
            this.throwOnStart = throwOnStart;
        }

        public void Start()
        {
            log.Add($"start:{name}");
            if (throwOnStart)
            {
                throw new InvalidOperationException($"start failed: {name}");
            }
        }

        public void Stop()
        {
            log.Add($"stop:{name}");
        }

        public void Dispose()
        {
            log.Add($"dispose:{name}");
        }
    }
}
