using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.Compilation;

namespace Mk.UnityAgentBridge.Editor
{
    /// <summary>
    /// 记录最近一轮编译的结果，供 /status 使用。结果持久化到 SessionState，
    /// 以便 domain reload（进 Play Mode 会触发）之后仍能读到编译是否成功。
    /// </summary>
    // Phase 2：不再用 [InitializeOnLoad] 自启，改由 Host composition root 的 CoreServicesLifecycle
    // 在 Start 时强制运行静态构造函数订阅 CompilationPipeline 事件；首次访问也会触发同样的订阅。
    public static class CompilationTracker
    {
        private const string LastCompilationKey = "Mk.UnityAgentBridge.LastCompilation";
        private const int MaxErrors = 50;

        private static readonly List<CompilationErrorEntry> PendingErrors = new List<CompilationErrorEntry>();

        static CompilationTracker()
        {
            CompilationPipeline.compilationStarted += OnCompilationStarted;
            CompilationPipeline.assemblyCompilationFinished += OnAssemblyCompilationFinished;
            CompilationPipeline.compilationFinished += OnCompilationFinished;
        }

        public static LastCompilationInfo LastCompilation
        {
            get
            {
                string json = SessionState.GetString(LastCompilationKey, string.Empty);
                if (string.IsNullOrEmpty(json))
                {
                    return LastCompilationInfo.NotYetCompiled();
                }

                LastCompilationInfo info = UnityEngine.JsonUtility.FromJson<LastCompilationInfo>(json);
                return info ?? LastCompilationInfo.NotYetCompiled();
            }
        }

        private static void OnCompilationStarted(object context)
        {
            PendingErrors.Clear();
        }

        private static void OnAssemblyCompilationFinished(string assemblyPath, CompilerMessage[] messages)
        {
            foreach (CompilerMessage compilerMessage in messages)
            {
                if (compilerMessage.type != CompilerMessageType.Error)
                {
                    continue;
                }

                if (PendingErrors.Count >= MaxErrors)
                {
                    continue;
                }

                PendingErrors.Add(new CompilationErrorEntry
                {
                    file = compilerMessage.file,
                    line = compilerMessage.line,
                    message = compilerMessage.message
                });
            }
        }

        private static void OnCompilationFinished(object context)
        {
            LastCompilationInfo info = new LastCompilationInfo
            {
                succeeded = PendingErrors.Count == 0,
                finishedAt = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
                errors = new List<CompilationErrorEntry>(PendingErrors)
            };
            SessionState.SetString(LastCompilationKey, UnityEngine.JsonUtility.ToJson(info));
        }

        [Serializable]
        public sealed class LastCompilationInfo
        {
            public bool succeeded;
            public string finishedAt;
            public List<CompilationErrorEntry> errors;

            public static LastCompilationInfo NotYetCompiled()
            {
                return new LastCompilationInfo
                {
                    succeeded = true,
                    finishedAt = string.Empty,
                    errors = new List<CompilationErrorEntry>()
                };
            }
        }
    }
}
