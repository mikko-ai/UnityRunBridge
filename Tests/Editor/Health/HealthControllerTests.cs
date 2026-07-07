using Mk.UnityAgentBridge.Editor.Health;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Health
{
    public sealed class HealthControllerTests
    {
        [SetUp]
        public void ResetState()
        {
            PrefabScanRunner.ResetForTests();
            JobManager.CompleteAllRunningForTests("test_reset");
        }

        [TearDown]
        public void TearDown()
        {
            PrefabScanRunner.ResetForTests();
            JobManager.CompleteAllRunningForTests("test_reset");
        }

        [Test]
        public void Routes_AreRegistered()
        {
            Assert.IsNotNull(RouteTable.Resolve("POST", "health/scan-prefabs", out _));
        }

        [Test]
        public void CapabilitiesResponse_DeclaresHealthCapability()
        {
            JsonValue response = CapabilitiesController.BuildResponse();
            bool hasHealth = false;
            foreach (JsonValue capability in response["capabilities"].Items)
            {
                if (capability.AsString == "health")
                {
                    hasHealth = true;
                }
            }

            Assert.IsTrue(hasHealth);
        }

        [Test]
        public void ScanPrefabs_ReturnsJobId_AndJobEventuallySucceeds()
        {
            object result = HealthController.ScanPrefabs(BridgeRequestContext.ForTests());

            Assert.IsInstanceOf<JsonValue>(result);
            JsonValue json = (JsonValue)result;
            Assert.IsTrue(json["ok"].AsBoolean);
            string jobId = json["jobId"].AsString;
            Assert.IsFalse(string.IsNullOrEmpty(jobId));

            // 项目里的真实 Prefab 数量未知，但整个扫描一定会在有限次 Tick 内收敛到终态。
            const int maxTicks = 1000;
            JobRecord record = JobManager.GetJob(jobId);
            for (int i = 0; i < maxTicks && record.Status == JobStatus.Running; i++)
            {
                PrefabScanRunner.Tick();
                record = JobManager.GetJob(jobId);
            }

            Assert.AreEqual(JobStatus.Succeeded, record.Status);
        }

        [Test]
        public void ScanPrefabs_WhileAlreadyScanning_ReturnsAlreadyScanning()
        {
            object first = HealthController.ScanPrefabs(BridgeRequestContext.ForTests());
            Assert.IsTrue(((JsonValue)first)["ok"].AsBoolean);
            Assert.IsTrue(PrefabScanRunner.IsRunning, "第一次调用应该已经开始扫描（除非项目里没有任何 Prefab）");

            object second = HealthController.ScanPrefabs(BridgeRequestContext.ForTests());
            BridgeResponse secondResponse = (BridgeResponse)second;

            Assert.IsFalse(secondResponse.ok);
            Assert.AreEqual("already_scanning", secondResponse.code);
        }
    }
}
