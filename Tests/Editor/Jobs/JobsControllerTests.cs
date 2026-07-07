using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Jobs
{
    public sealed class JobsControllerTests
    {
        [SetUp]
        public void ResetRunningJobs()
        {
            JobManager.CompleteAllRunningForTests("test setup reset");
        }

        [Test]
        public void Route_JobsWithId_IsRegistered()
        {
            RouteHandler handler = RouteTable.Resolve("GET", "jobs/job-abc-1234", out string pathParam);
            Assert.IsNotNull(handler);
            Assert.AreEqual("job-abc-1234", pathParam);
        }

        [Test]
        public void Route_UnknownJobId_ReturnsJobNotFound()
        {
            RouteHandler handler = RouteTable.Resolve("GET", "jobs/does-not-exist", out string pathParam);
            object result = handler(BridgeRequestContext.ForTests(pathParam));

            Assert.IsInstanceOf<BridgeResponse>(result);
            BridgeResponse response = (BridgeResponse)result;
            Assert.IsFalse(response.ok);
            Assert.AreEqual("job_not_found", response.code);
        }

        [Test]
        public void Route_KnownJobId_ReturnsJobPayload()
        {
            JobStartResult start = JobManager.StartJob("test-kind", handle => handle.Succeed("done"));

            RouteHandler handler = RouteTable.Resolve("GET", $"jobs/{start.JobId}", out string pathParam);
            object result = handler(BridgeRequestContext.ForTests(pathParam));

            Assert.IsInstanceOf<JsonValue>(result);
            JsonValue json = (JsonValue)result;
            Assert.AreEqual(start.JobId, json["job"]["id"].AsString);
            Assert.AreEqual("succeeded", json["job"]["status"].AsString);
        }

        [Test]
        public void CapabilitiesResponse_DeclaresJobsCapability()
        {
            JsonValue response = CapabilitiesController.BuildResponse();
            bool hasJobs = false;
            foreach (JsonValue capability in response["capabilities"].Items)
            {
                if (capability.AsString == "jobs")
                {
                    hasJobs = true;
                }
            }

            Assert.IsTrue(hasJobs);
        }
    }
}
