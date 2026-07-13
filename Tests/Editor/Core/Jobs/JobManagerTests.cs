using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Jobs;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Jobs
{
    /// <summary>
    /// JobManager 是跨测试共享的进程内单例，[SetUp] 里清空所有 running job，
    /// 保证每个测试方法看到的并发计数是干净的，不受其他测试/执行顺序影响。
    /// </summary>
    public sealed class JobManagerTests
    {
        [SetUp]
        public void ResetRunningJobs()
        {
            JobManager.CompleteAllRunningForTests("test setup reset");
        }

        [Test]
        public void StartJob_ThenSucceedSynchronously_RecordsSucceededResult()
        {
            JobStartResult start = JobManager.StartJob("test-kind", handle =>
            {
                handle.Succeed(new Dictionary<string, object> { ["path"] = "artifacts/x.png" });
            });

            Assert.IsTrue(start.Ok);
            JobRecord record = JobManager.GetJob(start.JobId);
            Assert.IsNotNull(record);
            Assert.AreEqual(JobStatus.Succeeded, record.Status);

            JsonValue response = JobManager.BuildJobResponse(record);
            Assert.AreEqual("succeeded", response["job"]["status"].AsString);
            Assert.AreEqual("artifacts/x.png", response["job"]["result"]["path"].AsString);
        }

        [Test]
        public void StartJob_ThenFail_RecordsErrorCodeAndMessage()
        {
            JobStartResult start = JobManager.StartJob("test-kind", handle =>
            {
                handle.Fail("capture_failed", "boom");
            });

            JobRecord record = JobManager.GetJob(start.JobId);
            Assert.AreEqual(JobStatus.Failed, record.Status);
            Assert.AreEqual("capture_failed", record.ErrorCode);
            Assert.AreEqual("boom", record.ErrorMessage);
        }

        [Test]
        public void StartJob_HandlerThrows_JobMarkedFailedWithInternalError()
        {
            JobStartResult start = JobManager.StartJob("test-kind", handle => throw new System.Exception("kaboom"));

            JobRecord record = JobManager.GetJob(start.JobId);
            Assert.AreEqual(JobStatus.Failed, record.Status);
            Assert.AreEqual("internal_error", record.ErrorCode);
            StringAssert.Contains("kaboom", record.ErrorMessage);
        }

        [Test]
        public void StartJob_HandlerDoesNotComplete_StaysRunning()
        {
            JobHandle capturedHandle = null;
            JobStartResult start = JobManager.StartJob("test-kind", handle => capturedHandle = handle);

            JobRecord record = JobManager.GetJob(start.JobId);
            Assert.AreEqual(JobStatus.Running, record.Status);

            // 清理：不留下永久 running 的 job 影响后续测试。
            capturedHandle.Fail("test_cleanup", "cleanup");
        }

        [Test]
        public void StartJob_ExceedingConcurrencyLimit_ReturnsTooManyJobs()
        {
            List<JobHandle> handles = new List<JobHandle>();
            for (int i = 0; i < 4; i++)
            {
                JobManager.StartJob("test-kind", handle => handles.Add(handle));
            }

            JobStartResult fifth = JobManager.StartJob("test-kind", handle => handles.Add(handle));

            Assert.IsFalse(fifth.Ok);
            Assert.AreEqual("too_many_jobs", fifth.ErrorCode);

            foreach (JobHandle handle in handles)
            {
                handle.Fail("test_cleanup", "cleanup");
            }
        }

        [Test]
        public void StartJob_AfterSlotFreed_CanStartAgain()
        {
            JobHandle handle = null;
            JobManager.StartJob("test-kind", h => handle = h);
            handle.Succeed(null);

            JobStartResult next = JobManager.StartJob("test-kind", h => h.Succeed(null));
            Assert.IsTrue(next.Ok);
        }

        [Test]
        public void GetJob_UnknownId_ReturnsNull()
        {
            Assert.IsNull(JobManager.GetJob("job-does-not-exist"));
            Assert.IsNull(JobManager.GetJob(null));
            Assert.IsNull(JobManager.GetJob(string.Empty));
        }

        [Test]
        public void CheckTimeouts_PastDeadline_MarksJobFailedWithJobTimeout()
        {
            JobStartResult start = JobManager.StartJob("test-kind", handle => { /* never completes */ }, timeoutSeconds: -1);
            JobManager.CheckTimeouts();

            JobRecord record = JobManager.GetJob(start.JobId);
            Assert.AreEqual(JobStatus.Failed, record.Status);
            Assert.AreEqual("job_timeout", record.ErrorCode);
        }

        [Test]
        public void CheckTimeouts_BeforeDeadline_LeavesJobRunning()
        {
            JobHandle handle = null;
            JobStartResult start = JobManager.StartJob("test-kind", h => handle = h, timeoutSeconds: 60);
            JobManager.CheckTimeouts();

            JobRecord record = JobManager.GetJob(start.JobId);
            Assert.AreEqual(JobStatus.Running, record.Status);

            handle.Fail("test_cleanup", "cleanup");
        }

        [Test]
        public void ParseRestoredRecords_RunningBecomesFailedInterruptedByReload()
        {
            string json = "[{\"id\":\"job-1\",\"kind\":\"screenshot\",\"status\":\"running\",\"errorCode\":null}]";
            List<JobRecord> restored = JobManager.ParseRestoredRecords(json);

            Assert.AreEqual(1, restored.Count);
            Assert.AreEqual(JobStatus.Failed, restored[0].Status);
            Assert.AreEqual("interrupted_by_reload", restored[0].ErrorCode);
        }

        [Test]
        public void ParseRestoredRecords_SucceededAndFailedPreserveState()
        {
            string json =
                "[{\"id\":\"job-2\",\"kind\":\"screenshot\",\"status\":\"succeeded\",\"errorCode\":null}," +
                "{\"id\":\"job-3\",\"kind\":\"screenshot\",\"status\":\"failed\",\"errorCode\":\"capture_failed\"}]";

            List<JobRecord> restored = JobManager.ParseRestoredRecords(json);

            Assert.AreEqual(2, restored.Count);
            Assert.AreEqual(JobStatus.Succeeded, restored[0].Status);
            Assert.IsNull(restored[0].ErrorCode);
            Assert.AreEqual(JobStatus.Failed, restored[1].Status);
            Assert.AreEqual("capture_failed", restored[1].ErrorCode);
        }

        [Test]
        public void ParseRestoredRecords_EmptyOrNullInput_ReturnsEmptyList()
        {
            Assert.AreEqual(0, JobManager.ParseRestoredRecords(null).Count);
            Assert.AreEqual(0, JobManager.ParseRestoredRecords(string.Empty).Count);
            Assert.AreEqual(0, JobManager.ParseRestoredRecords("not json").Count);
        }

        [Test]
        public void BuildJobResponse_NullResult_ReturnsJsonNull()
        {
            JobStartResult start = JobManager.StartJob("test-kind", handle => handle.Succeed(null));
            JobRecord record = JobManager.GetJob(start.JobId);

            JsonValue response = JobManager.BuildJobResponse(record);
            Assert.IsTrue(response["job"]["result"].IsNull);
            Assert.IsTrue(response["job"]["errorCode"].IsNull);
        }
    }
}
