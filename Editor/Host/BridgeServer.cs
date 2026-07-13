using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Lifecycle;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Host
{
    /// <summary>
    /// Composition root（Phase 2 起唯一保留 [InitializeOnLoad] 的入口）：负责组合根装配、生命周期
    /// 启停、domain reload 与退出处理。装配是事务性的——成功 Start 全部生命周期后才 publish active
    /// runtime、再开 HTTP；任一步失败则逆序 Stop 已 Start 的、Dispose 全部候选、清空未对外的 active。
    ///
    /// 网络承载拆到 <see cref="BridgeHttpHost"/>，鉴权/路由拆到 <see cref="BridgeRequestPipeline"/>，
    /// 响应序列化拆到 <see cref="ResponseSerializer"/>，装配拆到 <see cref="BridgeModuleBootstrap"/>。
    /// </summary>
    [InitializeOnLoad]
    internal static class BridgeServer
    {
        private const int MaxPortAttempts = 10;

        private static BridgeHttpHost httpHost;
        private static readonly List<IBridgeLifecycle> ActiveLifecycles = new List<IBridgeLifecycle>();

        static BridgeServer()
        {
            // session 恢复必须在装配前，保证 status/日志在首个请求前已就绪（与迁移前一致）。
            SessionService.RestoreActiveSession();

            if (!ComposeAndPublish())
            {
                return;
            }

            EditorApplication.update += OnEditorUpdate;
            AssemblyReloadEvents.beforeAssemblyReload += Stop;
            EditorApplication.quitting += StopForEditorQuit;

            StartHttp();
        }

        /// <summary>
        /// 发现生产候选 → 事务装配 → 追加 core 生命周期与 GET /capabilities → 逐个 Start 生命周期 →
        /// 成功后 publish active runtime。返回 false 表示装配失败（已完成回滚，未发布 active）。
        /// </summary>
        private static bool ComposeAndPublish()
        {
            BridgeComposition composition;
            try
            {
                BridgeModuleBootstrap.DiscoverProductionCandidates(out List<Type> adapterTypes, out List<Type> moduleTypes);
                composition = BridgeModuleBootstrap.ComposeSnapshot(adapterTypes, moduleTypes);
            }
            catch (BridgeCompositionException ex)
            {
                Debug.LogError($"Unity Agent Bridge 装配失败（未启动）：{ex.Message}");
                BridgeRuntime.ClearActive();
                return false;
            }

            BridgeRuntime runtime = composition.Runtime;

            // Host 最后注册 GET /capabilities：读同一 runtime 的 capability/route 快照，成为第 30 条路由。
            runtime.Routes.Map(
                "GET",
                "capabilities",
                _ => CapabilitiesResponseBuilder.Build(runtime.Capabilities.All(), runtime.Routes.ListRoutes()));

            // core 基础设施生命周期先于 Feature 生命周期启动。
            List<IBridgeLifecycle> lifecycles = new List<IBridgeLifecycle> { new CoreServicesLifecycle() };
            lifecycles.AddRange(composition.Lifecycles);

            try
            {
                BridgeModuleBootstrap.StartLifecycles(lifecycles);
            }
            catch (Exception ex)
            {
                BridgeModuleBootstrap.DisposeCandidates(composition.Candidates);
                BridgeRuntime.ClearActive();
                Debug.LogError($"Unity Agent Bridge 生命周期启动失败（已回滚，未发布）：{ex.Message}");
                return false;
            }

            ActiveLifecycles.Clear();
            ActiveLifecycles.AddRange(lifecycles);
            BridgeRuntime.Publish(runtime);
            return true;
        }

        private static void StartHttp()
        {
            if (httpHost != null && httpHost.IsRunning)
            {
                return;
            }

            int preferredPort = BridgeProjectConfig.Load().preferredPort;
            string token = BridgeInfoFile.GetOrCreateToken();
            httpHost = new BridgeHttpHost(BridgeRequestPipeline.Route);

            foreach (int candidatePort in BuildCandidatePorts(preferredPort, MaxPortAttempts))
            {
                if (httpHost.TryStart(BridgeConfig.BuildPrefix(candidatePort)))
                {
                    BridgeInfoFile.Write(candidatePort, token);
                    Debug.Log($"Unity Agent Bridge listening on {BridgeConfig.BuildPrefix(candidatePort)}");
                    return;
                }
            }

            Debug.LogWarning(
                $"Unity Agent Bridge could not bind any port in [{preferredPort}, {preferredPort + MaxPortAttempts - 1}]");
        }

        private static void OnEditorUpdate()
        {
            httpHost?.ProcessPendingRequests();
        }

        /// <summary>
        /// 每次 domain reload（beforeAssemblyReload）都会调用，只停监听线程与主线程队列订阅，
        /// 绝不删除 bridge.json——reload 后静态构造函数会重新装配并 Start() 覆盖写。
        /// 生命周期不在此显式 Stop：静态订阅随 domain reload 清空，下次装配重新建立（与迁移前一致）。
        /// </summary>
        public static void Stop()
        {
            EditorApplication.update -= OnEditorUpdate;
            AssemblyReloadEvents.beforeAssemblyReload -= Stop;
            EditorApplication.quitting -= StopForEditorQuit;

            httpHost?.Stop();
        }

        private static void StopForEditorQuit()
        {
            SessionService.EndSession();
            BridgeInfoFile.Delete();
            Stop();
        }

        /// <summary>
        /// 端口顺延候选列表：从 preferredPort 开始连续尝试 maxAttempts 个端口。
        /// 抽成纯函数便于 EditMode 测试覆盖，不依赖 HttpListener。
        /// </summary>
        internal static int[] BuildCandidatePorts(int preferredPort, int maxAttempts)
        {
            int[] ports = new int[maxAttempts];
            for (int i = 0; i < maxAttempts; i++)
            {
                ports[i] = preferredPort + i;
            }

            return ports;
        }

        /// <summary>
        /// 保留既有入口以兼容测试；实际解析已下沉到 Core 的 <see cref="RequestBodyParser"/>，
        /// 新增 Feature/Module 请直接调用 RequestBodyParser。
        /// </summary>
        internal static T ParseJsonOrNull<T>(string json) where T : class
        {
            return RequestBodyParser.ParseJsonOrNull<T>(json);
        }

        /// <summary>
        /// token 校验的纯函数版本，便于 EditMode 测试覆盖缺失/不匹配/匹配三种情况。
        /// </summary>
        internal static bool IsTokenValid(string providedToken, string expectedToken)
        {
            return !string.IsNullOrEmpty(providedToken)
                && !string.IsNullOrEmpty(expectedToken)
                && string.Equals(providedToken, expectedToken, StringComparison.Ordinal);
        }
    }
}
