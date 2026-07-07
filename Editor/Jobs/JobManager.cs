using System;
using System.Collections.Generic;
using UnityEditor;
using Mk.UnityAgentBridge.Editor.Json;

namespace Mk.UnityAgentBridge.Editor.Jobs
{
    internal enum JobStatus
    {
        Running,
        Succeeded,
        Failed
    }

    internal sealed class JobRecord
    {
        public string Id;
        public string Kind;
        public JobStatus Status;
        public string CreatedAt;
        public object Result;
        public string ErrorCode;
        public string ErrorMessage;
        public DateTime Deadline;
    }

    /// <summary>
    /// 承载跨帧/耗时操作（截图、profiling 采样窗口等）的异步 job：请求发起后立即返回 jobId，
    /// 结果通过 GET /jobs/{id} 轮询获得。内存字典保存全部状态；每次变更把精简摘要
    /// （id/kind/status/errorCode）写入 SessionState，domain reload 后据此把 running 恢复为 failed
    /// （跨 reload 续跑不做，报错清晰即可）。
    /// </summary>
    [InitializeOnLoad]
    internal static class JobManager
    {
        public const double DefaultTimeoutSeconds = 30;
        private const int MaxConcurrentRunning = 4;
        private const int MaxCompletedRetained = 20;
        private const string SessionStateKey = "UnityAgentBridge.Jobs";

        private static readonly Dictionary<string, JobRecord> Jobs = new Dictionary<string, JobRecord>(StringComparer.Ordinal);
        private static readonly List<string> CompletionOrder = new List<string>();

        static JobManager()
        {
            RestoreFromSessionState();
            TempObjectRegistry.RegisterCleanupHandler(OnTempObjectCleanup);
            EditorApplication.update += CheckTimeouts;
        }

        public static JobStartResult StartJob(string kind, Action<JobHandle> handler, double timeoutSeconds = DefaultTimeoutSeconds)
        {
            int runningCount = 0;
            foreach (JobRecord existing in Jobs.Values)
            {
                if (existing.Status == JobStatus.Running)
                {
                    runningCount++;
                }
            }

            if (runningCount >= MaxConcurrentRunning)
            {
                return JobStartResult.Failure("too_many_jobs", $"too many concurrent jobs running (max {MaxConcurrentRunning})");
            }

            string id = GenerateJobId();
            JobRecord record = new JobRecord
            {
                Id = id,
                Kind = kind,
                Status = JobStatus.Running,
                CreatedAt = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                Deadline = DateTime.UtcNow.AddSeconds(timeoutSeconds)
            };
            Jobs[id] = record;
            PersistSummary();

            try
            {
                handler(new JobHandle(id));
            }
            catch (Exception ex)
            {
                CompleteFailed(id, "internal_error", ex.Message);
            }

            return JobStartResult.Success(id);
        }

        /// <summary>
        /// Play Mode 下用隐藏 MonoBehaviour 承载 WaitForEndOfFrame；非 Play Mode 下没有稳定的帧渲染
        /// 时机可等，退化为强制推一次 player loop 后挂到下一次 EditorApplication.update tick 执行。
        /// </summary>
        public static void ScheduleEndOfFrame(Action callback)
        {
            if (EditorApplication.isPlaying)
            {
                EndOfFrameRunner.Schedule(callback);
                return;
            }

            EditorApplication.QueuePlayerLoopUpdate();
            EditorApplication.CallbackFunction wrapper = null;
            wrapper = () =>
            {
                EditorApplication.update -= wrapper;
                callback?.Invoke();
            };
            EditorApplication.update += wrapper;
        }

        /// <summary>
        /// 仅供 EditMode 测试使用：JobManager 是跨测试共享的进程内单例状态，
        /// 测试在 [SetUp] 里调用它把上一个测试遗留的 running job 清空，避免并发上限等
        /// 依赖计数的测试因执行顺序不同而抖动。
        /// </summary>
        internal static void CompleteAllRunningForTests(string reason)
        {
            List<string> runningIds = new List<string>();
            foreach (JobRecord record in Jobs.Values)
            {
                if (record.Status == JobStatus.Running)
                {
                    runningIds.Add(record.Id);
                }
            }

            foreach (string id in runningIds)
            {
                CompleteFailed(id, "test_reset", reason);
            }
        }

        public static JobRecord GetJob(string id)
        {
            return string.IsNullOrEmpty(id) ? null : Jobs.TryGetValue(id, out JobRecord record) ? record : null;
        }

        internal static void CompleteSucceeded(string jobId, object result)
        {
            if (!Jobs.TryGetValue(jobId, out JobRecord record) || record.Status != JobStatus.Running)
            {
                return;
            }

            record.Status = JobStatus.Succeeded;
            record.Result = result;
            OnJobCompleted(jobId);
        }

        internal static void CompleteFailed(string jobId, string errorCode, string errorMessage)
        {
            if (!Jobs.TryGetValue(jobId, out JobRecord record) || record.Status != JobStatus.Running)
            {
                return;
            }

            record.Status = JobStatus.Failed;
            record.ErrorCode = errorCode;
            record.ErrorMessage = errorMessage;
            OnJobCompleted(jobId);
        }

        private static void OnJobCompleted(string jobId)
        {
            CompletionOrder.Remove(jobId);
            CompletionOrder.Add(jobId);
            PruneCompleted();
            PersistSummary();
        }

        private static void PruneCompleted()
        {
            while (CompletionOrder.Count > MaxCompletedRetained)
            {
                string oldest = CompletionOrder[0];
                CompletionOrder.RemoveAt(0);
                Jobs.Remove(oldest);
            }
        }

        internal static void CheckTimeouts()
        {
            if (Jobs.Count == 0)
            {
                return;
            }

            DateTime now = DateTime.UtcNow;
            List<string> timedOut = null;
            foreach (JobRecord record in Jobs.Values)
            {
                if (record.Status == JobStatus.Running && now >= record.Deadline)
                {
                    (timedOut ??= new List<string>()).Add(record.Id);
                }
            }

            if (timedOut == null)
            {
                return;
            }

            foreach (string id in timedOut)
            {
                CompleteFailed(id, "job_timeout", $"job '{id}' timed out before completion");
            }
        }

        private static void OnTempObjectCleanup(string reason)
        {
            if (reason != "play_mode_exited")
            {
                return;
            }

            bool changed = false;
            foreach (JobRecord record in Jobs.Values)
            {
                if (record.Status == JobStatus.Running)
                {
                    record.Status = JobStatus.Failed;
                    record.ErrorCode = "play_mode_exited";
                    record.ErrorMessage = "play mode exited before job completed";
                    changed = true;
                }
            }

            if (changed)
            {
                PersistSummary();
            }
        }

        internal static JsonValue BuildJobResponse(JobRecord record)
        {
            JsonValue job = JsonValue.NewObject();
            job["id"] = record.Id;
            job["kind"] = record.Kind;
            job["status"] = StatusToString(record.Status);
            job["createdAt"] = record.CreatedAt ?? string.Empty;
            job["result"] = ToJsonValue(record.Result);
            job["errorCode"] = record.ErrorCode == null ? JsonValue.Null : JsonValue.FromString(record.ErrorCode);
            job["errorMessage"] = record.ErrorMessage == null ? JsonValue.Null : JsonValue.FromString(record.ErrorMessage);

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["job"] = job;
            return response;
        }

        private static JsonValue ToJsonValue(object value)
        {
            if (value == null)
            {
                return JsonValue.Null;
            }

            if (value is JsonValue jsonValue)
            {
                return jsonValue;
            }

            return JsonParser.Parse(JsonWriter.Serialize(value));
        }

        private static string StatusToString(JobStatus status)
        {
            return status switch
            {
                JobStatus.Running => "running",
                JobStatus.Succeeded => "succeeded",
                JobStatus.Failed => "failed",
                _ => "unknown"
            };
        }

        private static string GenerateJobId()
        {
            string timestamp = DateTime.UtcNow.ToString("yyyyMMddHHmmssfff");
            string random = Guid.NewGuid().ToString("N").Substring(0, 4);
            return $"job-{timestamp}-{random}";
        }

        private static void PersistSummary()
        {
            List<object> list = new List<object>();
            foreach (JobRecord record in Jobs.Values)
            {
                Dictionary<string, object> item = new Dictionary<string, object>
                {
                    ["id"] = record.Id,
                    ["kind"] = record.Kind ?? string.Empty,
                    ["status"] = StatusToString(record.Status),
                    ["errorCode"] = record.ErrorCode
                };
                list.Add(item);
            }

            SessionState.SetString(SessionStateKey, JsonWriter.Serialize(list));
        }

        private static void RestoreFromSessionState()
        {
            string json = SessionState.GetString(SessionStateKey, string.Empty);
            foreach (JobRecord record in ParseRestoredRecords(json))
            {
                Jobs[record.Id] = record;
                CompletionOrder.Add(record.Id);
            }

            PruneCompleted();
            PersistSummary();
        }

        /// <summary>
        /// 把 PersistSummary 写出的精简 JSON 还原成 JobRecord 列表：running → failed
        /// （errorCode: interrupted_by_reload），succeeded/failed 保留原状态与 errorCode。
        /// 抽成纯函数（不触碰 SessionState/Jobs 字典）便于 EditMode 测试直接验证转换规则。
        /// </summary>
        internal static List<JobRecord> ParseRestoredRecords(string json)
        {
            List<JobRecord> result = new List<JobRecord>();
            if (string.IsNullOrEmpty(json))
            {
                return result;
            }

            if (!JsonParser.TryParse(json, out JsonValue array, out _) || !array.IsArray)
            {
                return result;
            }

            foreach (JsonValue item in array.Items)
            {
                if (!item.IsObject)
                {
                    continue;
                }

                string id = item.GetString("id");
                if (string.IsNullOrEmpty(id))
                {
                    continue;
                }

                string statusText = item.GetString("status");
                bool wasRunning = statusText == "running";

                result.Add(new JobRecord
                {
                    Id = id,
                    Kind = item.GetString("kind", string.Empty),
                    Status = wasRunning ? JobStatus.Failed : ParseStatus(statusText),
                    ErrorCode = wasRunning ? "interrupted_by_reload" : item.GetString("errorCode"),
                    ErrorMessage = wasRunning ? "job interrupted by editor domain reload" : null,
                    CreatedAt = string.Empty,
                    Deadline = DateTime.MaxValue
                });
            }

            return result;
        }

        private static JobStatus ParseStatus(string text)
        {
            return text switch
            {
                "succeeded" => JobStatus.Succeeded,
                "failed" => JobStatus.Failed,
                _ => JobStatus.Failed
            };
        }
    }

    internal sealed class JobHandle
    {
        private readonly string jobId;

        internal JobHandle(string jobId)
        {
            this.jobId = jobId;
        }

        public string JobId => jobId;

        public void Succeed(object result) => JobManager.CompleteSucceeded(jobId, result);

        public void Fail(string errorCode, string errorMessage) => JobManager.CompleteFailed(jobId, errorCode, errorMessage);
    }

    internal readonly struct JobStartResult
    {
        public bool Ok { get; }
        public string JobId { get; }
        public string ErrorCode { get; }
        public string ErrorMessage { get; }

        private JobStartResult(bool ok, string jobId, string errorCode, string errorMessage)
        {
            Ok = ok;
            JobId = jobId;
            ErrorCode = errorCode;
            ErrorMessage = errorMessage;
        }

        public static JobStartResult Success(string jobId) => new JobStartResult(true, jobId, null, null);

        public static JobStartResult Failure(string errorCode, string errorMessage) =>
            new JobStartResult(false, null, errorCode, errorMessage);
    }
}
