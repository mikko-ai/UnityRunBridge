using System.IO;
using Mk.UnityAgentBridge.Editor.Build;
using NUnit.Framework;
using UnityEditor;

namespace Mk.UnityAgentBridge.Editor.Tests.Build
{
    /// <summary>
    /// BuildRunner.Build 本体调用 BuildPipeline.BuildPlayer，跑一次真实构建耗时很长，
    /// 也不适合作为自动化 EditMode 测试（README/计划里把「构建成功/失败报告正确」列为手工验收项）。
    /// 这里只覆盖不依赖真实构建的纯逻辑：命令行参数解析、场景列表过滤、失败报告 JSON 结构。
    /// </summary>
    public sealed class BuildRunnerTests
    {
        [Test]
        public void GetCommandLineArg_ReturnsNull_WhenArgNotPresent()
        {
            Assert.IsNull(BuildRunner.GetCommandLineArg("-doesNotExist"));
        }

        [Test]
        public void WriteFailureReport_WritesResultFailedWithMessage()
        {
            string path = Path.Combine(Path.GetTempPath(), $"build-report-{System.Guid.NewGuid():N}.json");
            try
            {
                BuildRunner.WriteFailureReport(path, "boom happened");

                Assert.IsTrue(File.Exists(path));
                string content = File.ReadAllText(path);
                StringAssert.Contains("\"result\":\"Failed\"", content.Replace(" ", string.Empty));
                StringAssert.Contains("boom happened", content);
            }
            finally
            {
                if (File.Exists(path))
                {
                    File.Delete(path);
                }
            }
        }

        [Test]
        public void GetEnabledScenePaths_OnlyReturnsEnabledScenes()
        {
            EditorBuildSettingsScene[] original = EditorBuildSettings.scenes;
            try
            {
                EditorBuildSettings.scenes = new[]
                {
                    new EditorBuildSettingsScene("Assets/UnityAgentBridgeTests_Enabled.unity", true),
                    new EditorBuildSettingsScene("Assets/UnityAgentBridgeTests_Disabled.unity", false),
                };

                string[] scenes = BuildRunner.GetEnabledScenePaths();

                Assert.AreEqual(1, scenes.Length);
                Assert.AreEqual("Assets/UnityAgentBridgeTests_Enabled.unity", scenes[0]);
            }
            finally
            {
                EditorBuildSettings.scenes = original;
            }
        }
    }
}
