using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Jobs;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Health
{
    /// <summary>
    /// POST /health/scan-prefabs 的执行体：遍历项目内全部 Prefab 资产，检测是否含缺失脚本引用
    /// （序列化时记录的脚本类型在磁盘上已找不到，对应 Component 在 GetComponents 里表现为 null）。
    /// 资产数量可能有几千个，一次性扫完会卡住主线程，所以拆成跨帧批处理：
    /// 静态类挂在 EditorApplication.update 上，每次 tick 最多处理 <see cref="BatchSize"/> 个 prefab；
    /// 设计上与 RecordingListener/MetricsSampler 一致——不用 MonoBehaviour（Editor 程序集里加不了），
    /// 也不做跨 domain reload 续跑（JobManager 会把中断的 job 标成 interrupted_by_reload，报错清晰即可）。
    /// </summary>
    internal static class PrefabScanRunner
    {
        internal const int BatchSize = 50;

        private static List<string> pendingPaths;
        private static List<string> assetsWithMissingScripts;
        private static int scannedCount;
        private static JobHandle activeHandle;
        private static bool isRunning;

        public static void Start(JobHandle handle)
        {
            StartWithPaths(handle, DiscoverPrefabPaths());
        }

        private static List<string> DiscoverPrefabPaths()
        {
            string[] guids = AssetDatabase.FindAssets("t:Prefab");
            List<string> paths = new List<string>(guids.Length);
            foreach (string guid in guids)
            {
                paths.Add(AssetDatabase.GUIDToAssetPath(guid));
            }

            return paths;
        }

        /// <summary>
        /// 供 EditMode 测试直接指定要扫描的资产路径列表，绕开 AssetDatabase.FindAssets——
        /// 这样批处理（BatchSize）行为可以用不存在的假路径造出任意数量的待扫描项来测试，
        /// 不依赖测试项目里恰好有多少个 Prefab；缺失脚本检测则可以只挂到几个手工构造的真实 prefab 上，
        /// 不受测试项目里其它 Prefab 资产的干扰。
        /// </summary>
        internal static void StartWithPaths(JobHandle handle, List<string> assetPaths)
        {
            // 自我保护：即便调用方（HealthController）漏了并发检查，也不能让第二次 Start
            // 覆盖掉正在进行的 pendingPaths/activeHandle——那会导致第一个 job 的 JobHandle
            // 永久悬空（直到 JobManager 超时），且 Tick 被重复订阅到 EditorApplication.update。
            if (isRunning)
            {
                return;
            }

            activeHandle = handle;
            pendingPaths = new List<string>(assetPaths);
            assetsWithMissingScripts = new List<string>();
            scannedCount = 0;
            isRunning = true;
            EditorApplication.update += Tick;
        }

        internal static void Tick()
        {
            if (!isRunning)
            {
                return;
            }

            int processed = 0;
            while (processed < BatchSize && pendingPaths.Count > 0)
            {
                int lastIndex = pendingPaths.Count - 1;
                string path = pendingPaths[lastIndex];
                pendingPaths.RemoveAt(lastIndex);
                ScanOne(path);
                processed++;
                scannedCount++;
            }

            if (pendingPaths.Count == 0)
            {
                Finish();
            }
        }

        private static void ScanOne(string path)
        {
            GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            if (prefab == null)
            {
                return;
            }

            foreach (Transform child in prefab.GetComponentsInChildren<Transform>(true))
            {
                if (NodeSerializer.HasMissingScript(child.gameObject))
                {
                    assetsWithMissingScripts.Add(path);
                    return;
                }
            }
        }

        private static void Finish()
        {
            EditorApplication.update -= Tick;
            isRunning = false;

            JobHandle handle = activeHandle;
            activeHandle = null;
            handle?.Succeed(new Dictionary<string, object>
            {
                ["scannedCount"] = scannedCount,
                ["assetsWithMissingScripts"] = assetsWithMissingScripts,
            });
        }

        internal static bool IsRunning => isRunning;

        internal static int PendingCount => pendingPaths?.Count ?? 0;

        /// <summary>仅供 EditMode 测试使用：清空静态状态，避免上一个测试遗留的 update 订阅串扰。</summary>
        internal static void ResetForTests()
        {
            if (isRunning)
            {
                EditorApplication.update -= Tick;
            }

            isRunning = false;
            pendingPaths = null;
            assetsWithMissingScripts = null;
            scannedCount = 0;
            activeHandle = null;
        }
    }
}
