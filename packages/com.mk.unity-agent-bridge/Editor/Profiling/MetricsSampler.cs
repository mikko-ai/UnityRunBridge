using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Json;
using Unity.Profiling;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Profiling
{
    /// <summary>
    /// 用 <see cref="ProfilerRecorder"/> 逐帧采样固定计数器集合（v1 不支持自定义配置）。
    /// 与 <see cref="Recording.RecordingListener"/> 同样用 <see cref="EditorApplication.update"/>
    /// 驱动而不是 MonoBehaviour：Editor-only 程序集无法把脚本挂到 GameObject 上。
    /// 计数器在不同 Unity 版本/渲染管线下可能不存在（<see cref="ProfilerRecorder.Valid"/> == false），
    /// 此时不采样该项、记入 <see cref="UnavailableMetrics"/>，绝不让 recorder 静默返回 0。
    /// </summary>
    internal static class MetricsSampler
    {
        private readonly struct MetricDefinition
        {
            public readonly string Name;
            public readonly ProfilerCategory Category;
            public readonly string StatName;
            public readonly bool IsNanoseconds;

            public MetricDefinition(string name, ProfilerCategory category, string statName, bool isNanoseconds = false)
            {
                Name = name;
                Category = category;
                StatName = statName;
                IsNanoseconds = isNanoseconds;
            }
        }

        private static readonly MetricDefinition[] Definitions =
        {
            new MetricDefinition("frameTimeMs", ProfilerCategory.Internal, "CPU Main Thread Frame Time", isNanoseconds: true),
            new MetricDefinition("gcAllocBytes", ProfilerCategory.Memory, "GC Allocated In Frame"),
            new MetricDefinition("drawCalls", ProfilerCategory.Render, "Draw Calls Count"),
            new MetricDefinition("setPassCalls", ProfilerCategory.Render, "SetPass Calls Count"),
            new MetricDefinition("triangles", ProfilerCategory.Render, "Triangles Count"),
            new MetricDefinition("totalMemoryBytes", ProfilerCategory.Memory, "Total Used Memory"),
            new MetricDefinition("gcMemoryBytes", ProfilerCategory.Memory, "GC Used Memory"),
        };

        private static readonly Dictionary<string, ProfilerRecorder> ActiveRecorders =
            new Dictionary<string, ProfilerRecorder>(StringComparer.Ordinal);

        private static Action<JsonValue> onSample;
        private static float startRealtime;

        internal static bool IsSampling { get; private set; }

        /// <summary>本次采样会话里因计数器不可用而跳过的指标名（只读快照，StartSampling 时确定）。</summary>
        internal static IReadOnlyList<string> UnavailableMetrics { get; private set; } = Array.Empty<string>();

        public static void StartSampling(Action<JsonValue> callback)
        {
            if (IsSampling)
            {
                return;
            }

            List<string> unavailable = new List<string>();
            foreach (MetricDefinition definition in Definitions)
            {
                ProfilerRecorder recorder = ProfilerRecorder.StartNew(definition.Category, definition.StatName, 1);
                if (recorder.Valid)
                {
                    ActiveRecorders[definition.Name] = recorder;
                }
                else
                {
                    recorder.Dispose();
                    unavailable.Add(definition.Name);
                }
            }

            UnavailableMetrics = unavailable;
            onSample = callback;
            startRealtime = Time.realtimeSinceStartup;
            IsSampling = true;
            EditorApplication.update += Tick;
        }

        public static void StopSampling()
        {
            if (!IsSampling)
            {
                return;
            }

            EditorApplication.update -= Tick;
            IsSampling = false;
            onSample = null;
            DisposeAllRecorders();
        }

        /// <summary>internal 而非 private：EditMode/PlayMode 测试直接调用它产出确定性的单帧样本，
        /// 不必等待真实的 EditorApplication.update 触发时机。</summary>
        internal static void Tick()
        {
            JsonValue sample = JsonValue.NewObject();
            sample["frame"] = Time.frameCount;
            sample["time"] = Time.realtimeSinceStartup - startRealtime;

            foreach (KeyValuePair<string, ProfilerRecorder> entry in ActiveRecorders)
            {
                long raw = entry.Value.LastValue;
                sample[entry.Key] = FindDefinition(entry.Key).IsNanoseconds ? raw / 1_000_000.0 : (double)raw;
            }

            onSample?.Invoke(sample);
        }

        private static MetricDefinition FindDefinition(string name)
        {
            foreach (MetricDefinition definition in Definitions)
            {
                if (definition.Name == name)
                {
                    return definition;
                }
            }

            throw new KeyNotFoundException(name);
        }

        private static void DisposeAllRecorders()
        {
            foreach (KeyValuePair<string, ProfilerRecorder> entry in ActiveRecorders)
            {
                entry.Value.Dispose();
            }

            ActiveRecorders.Clear();
        }

        /// <summary>仅供 EditMode 测试使用：把静态状态重置为未采样，避免测试之间互相污染。</summary>
        internal static void ResetForTests()
        {
            if (IsSampling)
            {
                EditorApplication.update -= Tick;
            }

            IsSampling = false;
            onSample = null;
            DisposeAllRecorders();
            UnavailableMetrics = Array.Empty<string>();
        }
    }
}
