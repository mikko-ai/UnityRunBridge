using System;
using System.Collections.Generic;
using System.Reflection;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;

namespace Mk.UnityAgentBridge.Editor.Host
{
    /// <summary>
    /// 事务装配的产物：本次候选 runtime、需要 Start 的生命周期（按引用去重）、
    /// 以及全部已构造候选（回滚时逆序 Dispose）。
    /// </summary>
    internal sealed class BridgeComposition
    {
        public BridgeRuntime Runtime;
        public List<IBridgeLifecycle> Lifecycles;
        public List<object> Candidates;
    }

    /// <summary>
    /// 组合根装配器：负责从生产程序集发现 [BridgeAdapter]/[BridgeModule]，并把它们组合成一份
    /// 候选 <see cref="BridgeRuntime"/>。装配是事务性的：任何一步失败（构造异常、重复路由、
    /// 重复 capability、服务单选冲突）都抛 <see cref="BridgeCompositionException"/>，不产出半成品。
    ///
    /// 发现（<see cref="DiscoverProductionCandidates"/>）与组合（<see cref="ComposeSnapshot"/>）分离：
    /// 组合只接受注入的候选类型、不校验 Attribute，便于 Host.Tests 注入 Fake 而不污染生产 TypeCache。
    /// </summary>
    internal static class BridgeModuleBootstrap
    {
        /// <summary>
        /// 通过 TypeCache 发现生产候选：带 [BridgeAdapter]/[BridgeModule] 的 class，且其所在程序集
        /// 带 [BridgeDiscoveryAssembly]。过滤掉 abstract / interface / 开放泛型 / 无合法无参构造的类型。
        /// 测试程序集不加 assembly marker，因此测试 Fake 不会被生产装配采集。
        /// </summary>
        public static void DiscoverProductionCandidates(out List<Type> adapterTypes, out List<Type> moduleTypes)
        {
            adapterTypes = new List<Type>();
            moduleTypes = new List<Type>();

            foreach (Type type in TypeCache.GetTypesWithAttribute<BridgeAdapterAttribute>())
            {
                if (IsConstructableProductionType(type) && HasDiscoveryMarker(type) && typeof(IBridgeAdapter).IsAssignableFrom(type))
                {
                    adapterTypes.Add(type);
                }
            }

            foreach (Type type in TypeCache.GetTypesWithAttribute<BridgeModuleAttribute>())
            {
                if (IsConstructableProductionType(type) && HasDiscoveryMarker(type) && typeof(IBridgeModule).IsAssignableFrom(type))
                {
                    moduleTypes.Add(type);
                }
            }
        }

        /// <summary>
        /// 把候选类型组合成候选 runtime：构造 → Adapter 先注册服务、Module 后注册路由/capability，
        /// Adapter 按 Priority 降序、Module 按 Order 升序稳定排序（同序用类型全名兜底）。
        /// 只有 IsAvailable==true 的 Module 才登记。不注册 GET /capabilities（由 Host 最后补）。
        /// </summary>
        public static BridgeComposition ComposeSnapshot(IReadOnlyList<Type> adapterTypes, IReadOnlyList<Type> moduleTypes)
        {
            BridgeRuntime runtime = new BridgeRuntime();
            List<object> candidates = new List<object>();

            List<IBridgeAdapter> adapters = ConstructAll<IBridgeAdapter>(adapterTypes, candidates);
            List<IBridgeModule> modules = ConstructAll<IBridgeModule>(moduleTypes, candidates);

            adapters.Sort((a, b) =>
            {
                if (a.Priority != b.Priority)
                {
                    return b.Priority.CompareTo(a.Priority);
                }

                return string.CompareOrdinal(TypeName(a), TypeName(b));
            });

            modules.Sort((a, b) =>
            {
                if (a.Order != b.Order)
                {
                    return a.Order.CompareTo(b.Order);
                }

                return string.CompareOrdinal(TypeName(a), TypeName(b));
            });

            try
            {
                foreach (IBridgeAdapter adapter in adapters)
                {
                    adapter.RegisterServices(runtime.Services);
                }

                List<IBridgeModule> availableModules = new List<IBridgeModule>();
                HashSet<string> declaredCapabilities = new HashSet<string>(StringComparer.Ordinal);
                foreach (IBridgeModule module in modules)
                {
                    if (!module.IsAvailable(runtime.Services))
                    {
                        continue;
                    }

                    string capability = module.Capability;
                    if (!string.IsNullOrWhiteSpace(capability) && !declaredCapabilities.Add(capability))
                    {
                        throw new BridgeCompositionException(
                            $"重复 capability：{capability}（由 {TypeName(module)} 再次声明）");
                    }

                    runtime.Capabilities.Declare(capability);
                    module.RegisterRoutes(runtime.Routes, runtime.Services);
                    availableModules.Add(module);
                }

                List<IBridgeLifecycle> lifecycles = CollectLifecycles(adapters, runtime.Services.AllServiceInstances(), availableModules);

                return new BridgeComposition
                {
                    Runtime = runtime,
                    Lifecycles = lifecycles,
                    Candidates = candidates
                };
            }
            catch (BridgeCompositionException)
            {
                DisposeCandidates(candidates);
                throw;
            }
            catch (BridgeServiceConflictException ex)
            {
                DisposeCandidates(candidates);
                throw new BridgeCompositionException($"服务单选冲突：{ex.Message}", ex);
            }
            catch (InvalidOperationException ex)
            {
                // InstanceRouteTable.Map 的重复路由。
                DisposeCandidates(candidates);
                throw new BridgeCompositionException($"路由装配失败：{ex.Message}", ex);
            }
            catch (Exception ex)
            {
                DisposeCandidates(candidates);
                throw new BridgeCompositionException($"装配阶段异常：{ex.Message}", ex);
            }
        }

        /// <summary>
        /// 顺序 Start 生命周期；任一 Start 抛出时逆序 Stop 已 Start 的，再把原异常向上抛。
        /// 抽成可测方法，Host.Tests 用 Fake 验证逆序回滚。
        /// </summary>
        public static void StartLifecycles(IReadOnlyList<IBridgeLifecycle> lifecycles)
        {
            List<IBridgeLifecycle> started = new List<IBridgeLifecycle>();
            try
            {
                foreach (IBridgeLifecycle lifecycle in lifecycles)
                {
                    lifecycle.Start();
                    started.Add(lifecycle);
                }
            }
            catch
            {
                for (int i = started.Count - 1; i >= 0; i--)
                {
                    try
                    {
                        started[i].Stop();
                    }
                    catch
                    {
                        // 回滚阶段忽略单个 Stop 异常。
                    }
                }

                throw;
            }
        }

        /// <summary>逆序 Dispose 全部候选，吞掉单个候选的 Dispose 异常，保证回滚尽力完成。</summary>
        public static void DisposeCandidates(IReadOnlyList<object> candidates)
        {
            if (candidates == null)
            {
                return;
            }

            for (int i = candidates.Count - 1; i >= 0; i--)
            {
                if (candidates[i] is IDisposable disposable)
                {
                    try
                    {
                        disposable.Dispose();
                    }
                    catch
                    {
                        // 回滚阶段忽略单个候选的 Dispose 异常。
                    }
                }
            }
        }

        private static List<T> ConstructAll<T>(IReadOnlyList<Type> types, List<object> candidates) where T : class
        {
            List<T> instances = new List<T>();
            if (types == null)
            {
                return instances;
            }

            foreach (Type type in types)
            {
                object instance;
                try
                {
                    instance = Activator.CreateInstance(type);
                }
                catch (Exception ex)
                {
                    DisposeCandidates(candidates);
                    throw new BridgeCompositionException($"候选构造失败：{type.FullName}：{ex.Message}", ex);
                }

                candidates.Add(instance);
                instances.Add((T)instance);
            }

            return instances;
        }

        private static List<IBridgeLifecycle> CollectLifecycles(
            IReadOnlyList<IBridgeAdapter> adapters,
            IReadOnlyList<object> serviceInstances,
            IReadOnlyList<IBridgeModule> availableModules)
        {
            List<IBridgeLifecycle> lifecycles = new List<IBridgeLifecycle>();
            HashSet<object> seen = new HashSet<object>();

            void TryAdd(object candidate)
            {
                if (candidate is IBridgeLifecycle lifecycle && seen.Add(lifecycle))
                {
                    lifecycles.Add(lifecycle);
                }
            }

            foreach (IBridgeAdapter adapter in adapters)
            {
                TryAdd(adapter);
            }

            foreach (object service in serviceInstances)
            {
                TryAdd(service);
            }

            foreach (IBridgeModule module in availableModules)
            {
                TryAdd(module);
            }

            return lifecycles;
        }

        private static bool IsConstructableProductionType(Type type)
        {
            return type != null
                && type.IsClass
                && !type.IsAbstract
                && !type.IsInterface
                && !type.IsGenericTypeDefinition
                && type.GetConstructor(Type.EmptyTypes) != null;
        }

        private static bool HasDiscoveryMarker(Type type)
        {
            return type.Assembly.GetCustomAttribute<BridgeDiscoveryAssemblyAttribute>() != null;
        }

        private static string TypeName(object instance)
        {
            return instance.GetType().FullName ?? string.Empty;
        }
    }
}
