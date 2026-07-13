using System;
using System.Collections.Generic;

namespace Mk.UnityAgentBridge.Editor.Contracts
{
    /// <summary>只读服务解析：Module/handler 通过它按类型解析已注册的服务实现。</summary>
    public interface IBridgeServiceResolver
    {
        bool TryGet<T>(out T service) where T : class;
        IReadOnlyList<T> GetAll<T>() where T : class;
    }

    /// <summary>可写服务注册：Adapter 在 RegisterServices 阶段通过它登记服务实现与优先级。</summary>
    public interface IBridgeServiceRegistry : IBridgeServiceResolver
    {
        void Add<T>(T service, int priority) where T : class;
    }

    /// <summary>Adapter 契约：封装某项可选 Unity 技术，向候选 Runtime 注册服务实现。</summary>
    public interface IBridgeAdapter
    {
        int Priority { get; }
        void RegisterServices(IBridgeServiceRegistry services);
    }

    /// <summary>capability Module 契约：声明能力标签、注册顺序、可用性判定与路由注册。</summary>
    public interface IBridgeModule
    {
        string Capability { get; }
        int Order { get; }
        bool IsAvailable(IBridgeServiceResolver services);
        void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services);
    }

    /// <summary>生命周期契约：由 Host composition root 统一 Start/Stop/Dispose。</summary>
    public interface IBridgeLifecycle : IDisposable
    {
        void Start();
        void Stop();
    }
}
