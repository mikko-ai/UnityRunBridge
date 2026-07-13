using Mk.UnityAgentBridge.Editor.Capture;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Gameplay;
using Mk.UnityAgentBridge.Editor.Health;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Interaction;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Profiling;
using Mk.UnityAgentBridge.Editor.Recording;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;

namespace Mk.UnityAgentBridge.Editor
{
    // Features 生产 Module：Order 复现 Phase 0 的 30 路由注册顺序（Host 最后追加 GET capabilities）。
    // Interaction / Recording 的 IsAvailable 分别依赖 IInteractionBackend / IRecordingSemanticBackend。

    /// <summary>core：status / refresh / play-stop-pause-resume / open-scene / session*。</summary>
    [BridgeModule]
    public sealed class CoreBridgeModule : IBridgeModule
    {
        public string Capability => "core";
        public int Order => 10;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "status", _ => EditorStateProvider.GetStatus());
            routes.Map("POST", "refresh", _ =>
            {
                AssetDatabase.Refresh();
                return BridgeResponse.Success("accepted", "asset refresh triggered");
            });
            routes.Map("POST", "play", _ => PlayModeController.EnterPlayMode());
            routes.Map("POST", "stop", _ => PlayModeController.ExitPlayMode());
            routes.Map("POST", "pause", _ => PlayModeController.Pause());
            routes.Map("POST", "resume", _ => PlayModeController.Resume());
            routes.Map("POST", "open-scene", ctx =>
            {
                OpenSceneRequest sceneRequest = RequestBodyParser.ParseJsonOrNull<OpenSceneRequest>(ctx.RawBody);
                if (sceneRequest == null)
                {
                    return BridgeResponse.Failure("invalid_request", "invalid open-scene request body");
                }

                return SceneController.OpenScene(sceneRequest.scenePath);
            });
            routes.Map("POST", "session/start", ctx =>
            {
                SessionStartRequest sessionRequest = RequestBodyParser.ParseJsonOrNull<SessionStartRequest>(ctx.RawBody);
                if (sessionRequest == null)
                {
                    return BridgeResponse.Failure("invalid_request", "invalid session start request");
                }

                return SessionService.StartSession(sessionRequest.sessionId, sessionRequest.sessionPath);
            });
            routes.Map("POST", "session/end", _ => SessionService.EndSession());
            routes.Map("GET", "session/status", _ => SessionService.GetStatus());
        }
    }

    /// <summary>jobs：GET /jobs/{id} 轮询。</summary>
    [BridgeModule]
    public sealed class JobsBridgeModule : IBridgeModule
    {
        public string Capability => "jobs";
        public int Order => 20;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "jobs/{id}", ctx =>
            {
                JobRecord record = JobManager.GetJob(ctx.PathParam);
                if (record == null)
                {
                    return BridgeResponse.Failure("job_not_found", $"job not found: {ctx.PathParam}");
                }

                return JobManager.BuildJobResponse(record);
            });
        }
    }

    /// <summary>hierarchy：roots / tree / find / ancestors / inspect。</summary>
    [BridgeModule]
    public sealed class HierarchyBridgeModule : IBridgeModule
    {
        public string Capability => "hierarchy";
        public int Order => 30;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "hierarchy/roots", _ => HierarchyController.Roots());
            routes.Map("GET", "hierarchy/tree", ctx => HierarchyController.Tree((BridgeRequestContext)ctx));
            routes.Map("GET", "hierarchy/find", ctx => HierarchyController.Find((BridgeRequestContext)ctx));
            routes.Map("GET", "hierarchy/ancestors", ctx => HierarchyController.Ancestors((BridgeRequestContext)ctx));
            routes.Map("GET", "hierarchy/inspect", ctx => HierarchyController.Inspect((BridgeRequestContext)ctx));
        }
    }

    /// <summary>capture：POST /capture/screenshot。</summary>
    [BridgeModule]
    public sealed class CaptureBridgeModule : IBridgeModule
    {
        public string Capability => "capture";
        public int Order => 40;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("POST", "capture/screenshot", ctx => CaptureController.CaptureScreenshot((BridgeRequestContext)ctx));
        }
    }

    /// <summary>interaction：click / input / set-value；无 IInteractionBackend 时整组不注册。</summary>
    [BridgeModule]
    public sealed class InteractionBridgeModule : IBridgeModule
    {
        public string Capability => "interaction";
        public int Order => 50;

        public bool IsAvailable(IBridgeServiceResolver services) =>
            services != null && services.TryGet(out IInteractionBackend _);

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            // 闭包捕获候选 Runtime 的 resolver，请求时不读可变全局 Active。
            IBridgeServiceResolver captured = services;
            routes.Map("POST", "interaction/click", ctx => InteractionController.Click((BridgeRequestContext)ctx, captured));
            routes.Map("POST", "interaction/input", ctx => InteractionController.Input((BridgeRequestContext)ctx, captured));
            routes.Map("POST", "interaction/set-value", ctx => InteractionController.SetValue((BridgeRequestContext)ctx, captured));
        }
    }

    /// <summary>gameplay：GET /gameplay/commands、POST /gameplay/invoke。</summary>
    [BridgeModule]
    public sealed class GameplayBridgeModule : IBridgeModule
    {
        public string Capability => "gameplay";
        public int Order => 60;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("GET", "gameplay/commands", ctx => GameplayController.ListCommands((BridgeRequestContext)ctx));
            routes.Map("POST", "gameplay/invoke", ctx => GameplayController.Invoke((BridgeRequestContext)ctx));
        }
    }

    /// <summary>
    /// recording：start / stop / status。需要 IRecordingSemanticBackend 才注册；
    /// 无 pointer backend 时仍注册，但 start 返回 no_input_backend。
    /// </summary>
    [BridgeModule]
    public sealed class RecordingBridgeModule : IBridgeModule, IBridgeLifecycle
    {
        public string Capability => "recording";
        public int Order => 70;

        public bool IsAvailable(IBridgeServiceResolver services) =>
            services != null && services.TryGet(out IRecordingSemanticBackend _);

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            IBridgeServiceResolver captured = services;
            routes.Map("POST", "recording/start", ctx => RecordingController.Start((BridgeRequestContext)ctx, captured));
            routes.Map("POST", "recording/stop", ctx => RecordingController.Stop((BridgeRequestContext)ctx));
            routes.Map("GET", "recording/status", ctx => RecordingController.Status((BridgeRequestContext)ctx));
        }

        public void Start() => RecordingController.EnsureInitialized();
        public void Stop() { }
        public void Dispose() { }
    }

    /// <summary>profiling：start / stop / status。</summary>
    [BridgeModule]
    public sealed class ProfilingBridgeModule : IBridgeModule, IBridgeLifecycle
    {
        public string Capability => "profiling";
        public int Order => 80;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("POST", "profiling/start", ctx => ProfilingController.Start((BridgeRequestContext)ctx));
            routes.Map("POST", "profiling/stop", ctx => ProfilingController.Stop((BridgeRequestContext)ctx));
            routes.Map("GET", "profiling/status", ctx => ProfilingController.Status((BridgeRequestContext)ctx));
        }

        public void Start() => ProfilingController.EnsureInitialized();
        public void Stop() { }
        public void Dispose() { }
    }

    /// <summary>health：POST /health/scan-prefabs。</summary>
    [BridgeModule]
    public sealed class HealthBridgeModule : IBridgeModule
    {
        public string Capability => "health";
        public int Order => 90;
        public bool IsAvailable(IBridgeServiceResolver services) => true;

        public void RegisterRoutes(IRouteRegistrar routes, IBridgeServiceResolver services)
        {
            routes.Map("POST", "health/scan-prefabs", ctx => HealthController.ScanPrefabs((BridgeRequestContext)ctx));
        }
    }
}
