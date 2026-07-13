using Mk.UnityAgentBridge.Editor.Jobs;
using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Contract
{
    /// <summary>
    /// 冻结 job 信封与错误码→HTTP 映射，保证 CLI 轮询与失败判定不被重构破坏。
    /// </summary>
    public sealed class JobContractTests
    {
        [SetUp]
        public void ResetJobs()
        {
            JobManager.CompleteAllRunningForTests("job-contract-setup");
        }

        [TearDown]
        public void TearDown()
        {
            JobManager.CompleteAllRunningForTests("job-contract-teardown");
        }

        [Test]
        public void BuildJobResponse_ExposesStableEnvelopeFields()
        {
            JobStartResult start = JobManager.StartJob("contract-probe", handle =>
            {
                JsonValue result = JsonValue.NewObject();
                result["path"] = "probe.png";
                result["width"] = 8;
                result["height"] = 4;
                JobManager.CompleteSucceeded(handle.JobId, result);
            });

            Assert.IsTrue(start.Ok);
            JobRecord record = JobManager.GetJob(start.JobId);
            Assert.IsNotNull(record);

            JsonValue response = JobManager.BuildJobResponse(record);
            Assert.IsTrue(response["ok"].AsBoolean);
            Assert.IsTrue(response.ContainsKey("job"));

            JsonValue job = response["job"];
            Assert.AreEqual(start.JobId, job["id"].AsString);
            Assert.AreEqual("contract-probe", job["kind"].AsString);
            Assert.AreEqual("succeeded", job["status"].AsString);
            Assert.IsFalse(string.IsNullOrEmpty(job["createdAt"].AsString));
            Assert.IsTrue(job.ContainsKey("result"));
            Assert.IsTrue(job.ContainsKey("errorCode"));
            Assert.IsTrue(job.ContainsKey("errorMessage"));
            Assert.IsTrue(job["errorCode"].IsNull);
            Assert.IsTrue(job["errorMessage"].IsNull);
            Assert.AreEqual("probe.png", job["result"]["path"].AsString);
            Assert.AreEqual(8, job["result"]["width"].AsInt);
            Assert.AreEqual(4, job["result"]["height"].AsInt);
        }

        [Test]
        public void BuildJobResponse_FailedJob_ExposesErrorFields()
        {
            JobStartResult start = JobManager.StartJob("contract-fail", handle =>
            {
                JobManager.CompleteFailed(handle.JobId, "capture_failed", "probe failure");
            });

            Assert.IsTrue(start.Ok);
            JsonValue response = JobManager.BuildJobResponse(JobManager.GetJob(start.JobId));
            JsonValue job = response["job"];

            Assert.AreEqual("failed", job["status"].AsString);
            Assert.AreEqual("capture_failed", job["errorCode"].AsString);
            Assert.AreEqual("probe failure", job["errorMessage"].AsString);
            Assert.IsTrue(job["result"].IsNull);
        }

        [Test]
        public void ErrorCodeHttpMapping_CoversStableExternalCodes()
        {
            Assert.AreEqual(401, BridgeErrorCodes.ResolveHttpStatus("unauthorized"));
            Assert.AreEqual(404, BridgeErrorCodes.ResolveHttpStatus("not_found"));
            Assert.AreEqual(404, BridgeErrorCodes.ResolveHttpStatus("job_not_found"));
            Assert.AreEqual(404, BridgeErrorCodes.ResolveHttpStatus("node_not_found"));
            Assert.AreEqual(404, BridgeErrorCodes.ResolveHttpStatus("command_not_found"));
            Assert.AreEqual(409, BridgeErrorCodes.ResolveHttpStatus("busy"));
            Assert.AreEqual(409, BridgeErrorCodes.ResolveHttpStatus("compilation_failed"));
            Assert.AreEqual(409, BridgeErrorCodes.ResolveHttpStatus("not_in_play_mode"));
            Assert.AreEqual(409, BridgeErrorCodes.ResolveHttpStatus("too_many_jobs"));
            Assert.AreEqual(422, BridgeErrorCodes.ResolveHttpStatus("invalid_request"));
            Assert.AreEqual(422, BridgeErrorCodes.ResolveHttpStatus("no_input_backend"));
            Assert.AreEqual(422, BridgeErrorCodes.ResolveHttpStatus("ambiguous_component"));
            Assert.AreEqual(403, BridgeErrorCodes.ResolveHttpStatus("gameplay_disabled"));
            Assert.AreEqual(403, BridgeErrorCodes.ResolveHttpStatus("capture_disabled"));
            Assert.AreEqual(429, BridgeErrorCodes.ResolveHttpStatus("capture_quota_exceeded"));
            Assert.AreEqual(500, BridgeErrorCodes.ResolveHttpStatus("internal_error"));
            Assert.AreEqual(500, BridgeErrorCodes.ResolveHttpStatus("capture_failed"));
            Assert.AreEqual(500, BridgeErrorCodes.ResolveHttpStatus("invoke_failed"));
            Assert.IsTrue(BridgeErrorCodes.IsRegistered("no_input_backend"));
            Assert.IsTrue(BridgeErrorCodes.IsRegistered("already_recording"));
            Assert.IsTrue(BridgeErrorCodes.IsRegistered("already_profiling"));
        }
    }
}
