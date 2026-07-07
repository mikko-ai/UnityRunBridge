using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Routing;

namespace Mk.UnityAgentBridge.Editor.Health
{
    /// <summary>
    /// unityctl health 的 missing_scripts 检查项用到的唯一 Bridge 路由。
    /// 已加载场景的缺失脚本检测复用现有的 GET /hierarchy/find?missingScript=true，
    /// 这里只补全「项目里全部 Prefab 资产」这一层——resources/prefabs 不一定被任何场景引用，
    /// 只看已加载场景的 hierarchy 会漏掉未被引用或还没加载的 prefab。
    /// </summary>
    internal static class HealthController
    {
        public static void RegisterRoutes()
        {
            CapabilityRegistry.Declare("health");
            RouteTable.Register("POST", "health/scan-prefabs", ScanPrefabs);
        }

        internal static object ScanPrefabs(BridgeRequestContext ctx)
        {
            // PrefabScanRunner 是单例静态状态（不像 JobManager 那样每个 job 独立隔离），
            // 并发调用会互相覆盖 pendingPaths/assetsWithMissingScripts 并重复订阅 EditorApplication.update，
            // 所以在进入 JobManager 之前就必须先拒绝第二次并发扫描。
            if (PrefabScanRunner.IsRunning)
            {
                return BridgeResponse.Failure("already_scanning", "已经在扫描 Prefab 中，请等待当前扫描完成后重试");
            }

            JobStartResult start = JobManager.StartJob(
                "scan-prefabs",
                PrefabScanRunner.Start,
                timeoutSeconds: 120);

            if (!start.Ok)
            {
                return BridgeResponse.Failure(start.ErrorCode, start.ErrorMessage);
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["jobId"] = start.JobId;
            return response;
        }
    }
}
