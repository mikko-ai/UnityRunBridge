using System;
using System.Collections.Generic;
using System.IO;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Build
{
    /// <summary>
    /// batchmode 构建入口，经 `-executeMethod Mk.UnityAgentBridge.Editor.Build.BuildRunner.Build`
    /// 调用（必须是 public static，供 Unity 反射调用）。完全独立于 Bridge/HTTP：CLI 直接 spawn
    /// 一个新的 Unity 进程做构建，不与正在跑的 Editor 实例共享任何状态。目标平台由 Unity 原生
    /// `-buildTarget &lt;target&gt;` 决定（不自定义参数），保证脚本编译符号与目标平台一致——
    /// 本类只读 `-agentBuildOutput`/`-agentReportPath` 两个自定义参数、执行构建、写报告 JSON，
    /// 并显式调用 <see cref="EditorApplication.Exit"/> 控制退出码
    /// （BuildPipeline.BuildPlayer 失败不会让进程天然返回非 0）。
    /// </summary>
    public static class BuildRunner
    {
        private const string BuildOutputArg = "-agentBuildOutput";
        private const string ReportPathArg = "-agentReportPath";

        public static void Build()
        {
            string reportPath = GetCommandLineArg(ReportPathArg);
            string outputPath = GetCommandLineArg(BuildOutputArg);

            if (string.IsNullOrEmpty(reportPath))
            {
                // 没有报告路径就没法把失败原因传回去，只能靠退出码 + Unity 自身的构建日志。
                Debug.LogError($"Unity Agent Bridge BuildRunner: 缺少 {ReportPathArg} 参数");
                EditorApplication.Exit(1);
                return;
            }

            if (string.IsNullOrEmpty(outputPath))
            {
                WriteFailureReport(reportPath, $"缺少 {BuildOutputArg} 参数");
                EditorApplication.Exit(1);
                return;
            }

            try
            {
                DateTime startedAt = DateTime.UtcNow;
                BuildTarget target = EditorUserBuildSettings.activeBuildTarget;
                BuildPlayerOptions options = new BuildPlayerOptions
                {
                    scenes = GetEnabledScenePaths(),
                    locationPathName = outputPath,
                    target = target,
                    targetGroup = BuildPipeline.GetBuildTargetGroup(target),
                    options = BuildOptions.None,
                };

                BuildReport report = BuildPipeline.BuildPlayer(options);
                long durationMs = (long)(DateTime.UtcNow - startedAt).TotalMilliseconds;

                WriteReport(reportPath, report, durationMs);
                EditorApplication.Exit(report.summary.result == BuildResult.Succeeded ? 0 : 1);
            }
            catch (Exception ex)
            {
                // 构建过程抛异常（多半是配置错误，比如场景丢失）时也要先写报告再退出，
                // 不能让调用方只拿到一个裸的非 0 退出码。
                WriteFailureReport(reportPath, ex.Message);
                EditorApplication.Exit(1);
            }
        }

        internal static string[] GetEnabledScenePaths()
        {
            List<string> scenes = new List<string>();
            foreach (EditorBuildSettingsScene scene in EditorBuildSettings.scenes)
            {
                if (scene.enabled)
                {
                    scenes.Add(scene.path);
                }
            }

            return scenes.ToArray();
        }

        internal static string GetCommandLineArg(string name)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (string.Equals(args[i], name, StringComparison.Ordinal))
                {
                    return args[i + 1];
                }
            }

            return null;
        }

        internal static JsonValue BuildReportJson(BuildReport report, long durationMs)
        {
            JsonValue json = JsonValue.NewObject();
            json["result"] = report.summary.result.ToString();
            json["durationMs"] = durationMs;
            json["outputPath"] = report.summary.outputPath ?? string.Empty;
            json["sizeBytes"] = (long)report.summary.totalSize;

            JsonValue errors = JsonValue.NewArray();
            JsonValue warnings = JsonValue.NewArray();
            JsonValue steps = JsonValue.NewArray();

            foreach (BuildStep step in report.steps)
            {
                JsonValue stepJson = JsonValue.NewObject();
                stepJson["name"] = step.name;
                stepJson["durationMs"] = (long)step.duration.TotalMilliseconds;
                steps.Add(stepJson);

                if (step.messages == null)
                {
                    continue;
                }

                foreach (BuildStepMessage message in step.messages)
                {
                    if (message.type == LogType.Error || message.type == LogType.Exception || message.type == LogType.Assert)
                    {
                        errors.Add(message.content);
                    }
                    else if (message.type == LogType.Warning)
                    {
                        warnings.Add(message.content);
                    }
                }
            }

            json["errors"] = errors;
            json["warnings"] = warnings;
            json["steps"] = steps;
            return json;
        }

        private static void WriteReport(string reportPath, BuildReport report, long durationMs)
        {
            WriteReportFile(reportPath, BuildReportJson(report, durationMs));
        }

        internal static void WriteFailureReport(string reportPath, string message, long durationMs = 0)
        {
            JsonValue json = JsonValue.NewObject();
            json["result"] = BuildResult.Failed.ToString();
            json["durationMs"] = durationMs;
            json["outputPath"] = string.Empty;
            json["sizeBytes"] = 0;

            JsonValue errors = JsonValue.NewArray();
            errors.Add(message ?? "unknown build error");
            json["errors"] = errors;
            json["warnings"] = JsonValue.NewArray();
            json["steps"] = JsonValue.NewArray();

            WriteReportFile(reportPath, json);
        }

        private static void WriteReportFile(string reportPath, JsonValue json)
        {
            try
            {
                string directory = Path.GetDirectoryName(reportPath);
                if (!string.IsNullOrEmpty(directory))
                {
                    Directory.CreateDirectory(directory);
                }

                File.WriteAllText(reportPath, json.ToString());
            }
            catch (Exception ex)
            {
                Debug.LogError($"Unity Agent Bridge BuildRunner: 写入报告失败：{ex.Message}");
            }
        }
    }
}
