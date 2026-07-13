using System;
using System.Collections.Generic;
using System.IO;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Profiling
{
    /// <summary>
    /// 采样状态机 + 路由 handler。逐帧样本经 <see cref="MetricsSampler"/> 产出，本类负责
    /// 按 60 帧批量落盘 metrics.jsonl（避免逐帧 IO），以及 stop 时读回全部样本计算聚合值。
    /// domain reload / 退出 Play Mode / Editor 退出时如实上报 interrupted（同 2.3 录制的处理），
    /// 尚未落盘的批次会随静态状态一起丢失——这是设计取舍，不做额外持久化。
    /// </summary>
    // 不再用 [InitializeOnLoad] 自启，改由 ProfilingBridgeModule 的生命周期
    // 在 Host Start 时调用 EnsureInitialized() 触发静态构造函数完成 TempObjectRegistry 清理钩子订阅。
    internal static class ProfilingController
    {
        internal const string StateIdle = "idle";
        internal const string StateProfiling = "profiling";
        internal const string StateInterrupted = "interrupted";

        private const int FlushBatchSize = 60;

        private const string StateKey = "Mk.UnityAgentBridge.Profiling.State";
        private const string MetricsPathKey = "Mk.UnityAgentBridge.Profiling.MetricsPath";
        private const string FrameCountKey = "Mk.UnityAgentBridge.Profiling.FrameCount";

        private static readonly List<string> PendingLines = new List<string>();

        static ProfilingController()
        {
            TempObjectRegistry.RegisterCleanupHandler(OnTempObjectCleanup);
        }

        /// <summary>由 ProfilingBridgeModule 生命周期在 Host Start 时调用，触发静态构造函数
        /// 注册 TempObjectRegistry 清理钩子（等价于原先的 [InitializeOnLoad]）。</summary>
        internal static void EnsureInitialized()
        {
        }

        internal static object Start(BridgeRequestContext ctx)
        {
            string editorState = CurrentEditorState();
            if (editorState != "playing")
            {
                return BridgeResponse.Failure("not_in_play_mode", $"该操作需要 Play Mode（当前 editorState={editorState}）");
            }

            if (CurrentState() == StateProfiling)
            {
                return BridgeResponse.Failure("already_profiling", "已经在采样中，请先调用 POST /profiling/stop");
            }

            JsonValue body = ctx.Body;
            string targetDirectoryRaw = body != null && body.TryGetString("targetDirectory", out string dirValue)
                ? dirValue
                : null;

            string projectRoot = ArtifactPathGuard.GetProjectRoot();
            string targetDirectory = string.IsNullOrWhiteSpace(targetDirectoryRaw)
                ? ArtifactPathGuard.ResolveArtifactDirectory()
                : targetDirectoryRaw;

            if (!ArtifactPathGuard.IsAllowedArtifactPath(projectRoot, targetDirectory))
            {
                return BridgeResponse.Failure(
                    "invalid_argument", "targetDirectory must be under .unity-agent/sessions or .unity-agent/scratch");
            }

            Directory.CreateDirectory(targetDirectory);
            string metricsPath = Path.Combine(targetDirectory, "metrics.jsonl");
            // 覆盖式创建：同名旧文件会被截断，避免把上一次采样的帧和这一次混在一起。
            File.WriteAllText(metricsPath, string.Empty);

            PendingLines.Clear();
            MetricsSampler.StartSampling(sample => AppendSample(metricsPath, sample));

            SessionState.SetString(StateKey, StateProfiling);
            SessionState.SetString(MetricsPathKey, metricsPath);
            SessionState.SetInt(FrameCountKey, 0);

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["metricsPath"] = metricsPath;
            response["unavailableMetrics"] = ToJsonArray(MetricsSampler.UnavailableMetrics);
            return response;
        }

        internal static object Stop(BridgeRequestContext ctx)
        {
            string state = CurrentState();
            if (state == StateIdle)
            {
                JsonValue idleResponse = JsonValue.NewObject();
                idleResponse["ok"] = true;
                idleResponse["code"] = "not_profiling";
                idleResponse["metricsPath"] = JsonValue.Null;
                idleResponse["frameCount"] = 0;
                idleResponse["interrupted"] = false;
                idleResponse["aggregates"] = JsonValue.NewObject();
                return idleResponse;
            }

            string metricsPath = SessionState.GetString(MetricsPathKey, string.Empty);
            bool wasInterrupted = state == StateInterrupted;

            MetricsSampler.StopSampling();
            FlushPending(metricsPath);
            int frameCount = SessionState.GetInt(FrameCountKey, 0);
            JsonValue aggregates = ComputeAggregates(metricsPath);

            SessionState.SetString(StateKey, StateIdle);
            SessionState.EraseString(MetricsPathKey);
            SessionState.EraseInt(FrameCountKey);

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["metricsPath"] = metricsPath;
            response["frameCount"] = frameCount;
            response["interrupted"] = wasInterrupted;
            response["aggregates"] = aggregates;
            return response;
        }

        internal static object Status(BridgeRequestContext ctx)
        {
            string state = CurrentState();

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["profiling"] = state == StateProfiling;
            response["interrupted"] = state == StateInterrupted;
            response["frameCount"] = SessionState.GetInt(FrameCountKey, 0);
            response["metricsPath"] = state == StateIdle
                ? JsonValue.Null
                : JsonValue.FromString(SessionState.GetString(MetricsPathKey, string.Empty));
            return response;
        }

        internal static string CurrentState() => SessionState.GetString(StateKey, StateIdle);

        /// <summary>仅供 EditMode 测试使用：模拟 domain reload / 退出 Play Mode 打断采样。</summary>
        internal static void SimulateInterruptionForTests(string reason) => OnTempObjectCleanup(reason);

        /// <summary>仅供 EditMode 测试使用：把状态机重置为 idle，避免测试之间通过 SessionState 互相污染。</summary>
        internal static void ResetForTests()
        {
            MetricsSampler.ResetForTests();
            PendingLines.Clear();
            SessionState.EraseString(StateKey);
            SessionState.EraseString(MetricsPathKey);
            SessionState.EraseInt(FrameCountKey);
        }

        private static void AppendSample(string metricsPath, JsonValue sample)
        {
            PendingLines.Add(sample.ToString());
            SessionState.SetInt(FrameCountKey, SessionState.GetInt(FrameCountKey, 0) + 1);
            if (PendingLines.Count >= FlushBatchSize)
            {
                FlushPending(metricsPath);
            }
        }

        private static void FlushPending(string metricsPath)
        {
            if (PendingLines.Count == 0 || string.IsNullOrEmpty(metricsPath))
            {
                return;
            }

            try
            {
                File.AppendAllText(metricsPath, string.Join("\n", PendingLines) + "\n");
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"Unity Agent Bridge: 写入 metrics.jsonl 失败：{ex.Message}");
            }

            PendingLines.Clear();
        }

        /// <summary>
        /// 逐行读回 metrics.jsonl 计算每个指标的 avg/max/p95。p95 用最近邻取整（ceil(0.95*n)-1，
        /// clamp 到合法下标），不做插值——采样量通常足够大，简单实现已经够用。
        /// </summary>
        private static JsonValue ComputeAggregates(string metricsPath)
        {
            JsonValue aggregates = JsonValue.NewObject();
            if (string.IsNullOrEmpty(metricsPath) || !File.Exists(metricsPath))
            {
                return aggregates;
            }

            Dictionary<string, List<double>> valuesByMetric = new Dictionary<string, List<double>>(StringComparer.Ordinal);
            foreach (string line in File.ReadAllLines(metricsPath))
            {
                if (string.IsNullOrWhiteSpace(line))
                {
                    continue;
                }

                if (!JsonParser.TryParse(line, out JsonValue row, out _) || !row.IsObject)
                {
                    continue;
                }

                foreach (KeyValuePair<string, JsonValue> property in row.Properties)
                {
                    if (property.Key == "frame" || property.Key == "time" || !property.Value.IsNumber)
                    {
                        continue;
                    }

                    if (!valuesByMetric.TryGetValue(property.Key, out List<double> values))
                    {
                        values = new List<double>();
                        valuesByMetric[property.Key] = values;
                    }

                    values.Add(property.Value.AsDouble);
                }
            }

            foreach (KeyValuePair<string, List<double>> entry in valuesByMetric)
            {
                List<double> sorted = new List<double>(entry.Value);
                sorted.Sort();

                JsonValue stat = JsonValue.NewObject();
                stat["avg"] = Average(sorted);
                stat["max"] = sorted[sorted.Count - 1];
                stat["p95"] = Percentile(sorted, 0.95);
                aggregates[entry.Key] = stat;
            }

            return aggregates;
        }

        private static double Average(List<double> values)
        {
            if (values.Count == 0)
            {
                return 0;
            }

            double sum = 0;
            foreach (double value in values)
            {
                sum += value;
            }

            return sum / values.Count;
        }

        private static double Percentile(List<double> sortedValues, double percentile)
        {
            if (sortedValues.Count == 0)
            {
                return 0;
            }

            int index = (int)Math.Ceiling(percentile * sortedValues.Count) - 1;
            index = Math.Max(0, Math.Min(sortedValues.Count - 1, index));
            return sortedValues[index];
        }

        private static JsonValue ToJsonArray(IReadOnlyList<string> values)
        {
            JsonValue array = JsonValue.NewArray();
            foreach (string value in values)
            {
                array.Add(value);
            }

            return array;
        }

        /// <summary>
        /// domain reload 会连带清空 MetricsSampler 的静态订阅状态；退出 Play Mode / Editor 退出
        /// 则显式调用 StopSampling() 停止轮询并释放 ProfilerRecorder 句柄。三种情况下都如实标记
        /// interrupted，未落盘的批次按设计丢弃（详见类注释）。
        /// </summary>
        private static void OnTempObjectCleanup(string reason)
        {
            MetricsSampler.StopSampling();
            if (CurrentState() == StateProfiling)
            {
                SessionState.SetString(StateKey, StateInterrupted);
            }
        }

        private static string CurrentEditorState()
        {
            return EditorStateProvider.DeriveState(
                EditorApplication.isCompiling,
                EditorApplication.isUpdating,
                EditorApplication.isPlaying,
                EditorApplication.isPaused,
                EditorApplication.isPlayingOrWillChangePlaymode);
        }
    }
}
