using System.Collections;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Profiling;
using NUnit.Framework;
using UnityEngine.TestTools;

namespace Mk.UnityAgentBridge.Editor.Tests.Profiling
{
    // MetricsSampler 是纯静态类（同 RecordingListener 的设计取舍：Editor-only 程序集无法
    // AddComponent），但 ProfilerRecorder 的渲染类计数器（Draw Calls/SetPass Calls 等）只在
    // Play Mode 下才有意义，因此用 UnityTest + EnterPlayMode。Tick() 是 internal，测试直接
    // 调用它产出确定性的单帧样本，不依赖真实的 EditorApplication.update 触发时机。
    public sealed class MetricsSamplerTests
    {
        [SetUp]
        public void ResetSampler()
        {
            MetricsSampler.ResetForTests();
        }

        [TearDown]
        public void TearDown()
        {
            MetricsSampler.ResetForTests();
        }

        [UnityTest]
        public IEnumerator StartSampling_TickProducesSampleWithFrameAndTimeAndAvailableMetrics()
        {
            yield return new EnterPlayMode();

            List<JsonValue> samples = new List<JsonValue>();
            MetricsSampler.StartSampling(samples.Add);

            Assert.IsTrue(MetricsSampler.IsSampling);

            yield return null;
            MetricsSampler.Tick();

            Assert.AreEqual(1, samples.Count);
            JsonValue sample = samples[0];
            Assert.IsTrue(sample.ContainsKey("frame"));
            Assert.IsTrue(sample.ContainsKey("time"));

            // A valid recorder may have no data yet (especially in batch mode).
            Assert.LessOrEqual(sample.Count - 2, 7 - MetricsSampler.UnavailableMetrics.Count);
            foreach (string unavailable in MetricsSampler.UnavailableMetrics)
            {
                Assert.IsFalse(sample.ContainsKey(unavailable));
            }

            MetricsSampler.StopSampling();
            yield return new ExitPlayMode();
        }

        [UnityTest]
        public IEnumerator StopSampling_ReleasesRecordersAndStopsAcceptingTicks()
        {
            yield return new EnterPlayMode();

            List<JsonValue> samples = new List<JsonValue>();
            MetricsSampler.StartSampling(samples.Add);
            yield return null;
            MetricsSampler.StopSampling();

            Assert.IsFalse(MetricsSampler.IsSampling);

            yield return new ExitPlayMode();
        }

        [Test]
        public void StartSampling_TwiceInARow_SecondCallIsNoOp()
        {
            List<JsonValue> firstSamples = new List<JsonValue>();
            List<JsonValue> secondSamples = new List<JsonValue>();

            MetricsSampler.StartSampling(firstSamples.Add);
            MetricsSampler.StartSampling(secondSamples.Add);
            Assert.IsTrue(MetricsSampler.IsSampling);

            MetricsSampler.Tick();

            // 第二次 StartSampling 是 no-op：只有第一个回调仍然订阅。
            Assert.AreEqual(1, firstSamples.Count);
            Assert.AreEqual(0, secondSamples.Count);

            MetricsSampler.StopSampling();
        }

        [Test]
        public void ResetForTests_ClearsStateEvenWithoutStopSampling()
        {
            MetricsSampler.StartSampling(_ => { });
            Assert.IsTrue(MetricsSampler.IsSampling);

            MetricsSampler.ResetForTests();

            Assert.IsFalse(MetricsSampler.IsSampling);
            Assert.AreEqual(0, MetricsSampler.UnavailableMetrics.Count);
        }
    }
}
