using System.IO;
using NUnit.Framework;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Tests.Composition
{
    /// <summary>
    /// 输入 fixture 探针：读取工程 Assets/MkBridgeInputFixture.txt（由 create-unity-test-fixture.sh 写入），
    /// 确认 ENABLE_LEGACY_INPUT_MANAGER / ENABLE_INPUT_SYSTEM 与 fixture 名一致。
    /// </summary>
    public sealed class InputDefinesProbeTests
    {
        private static string ReadExpectedInputMode()
        {
            string path = Path.Combine(Application.dataPath, "MkBridgeInputFixture.txt");
            Assert.IsTrue(File.Exists(path), $"缺少 fixture 标记文件：{path}");
            return File.ReadAllText(path).Trim().ToLowerInvariant();
        }

        [Test]
        public void InputDefines_MatchFixtureMarker()
        {
            string expected = ReadExpectedInputMode();
            bool hasLegacy =
#if ENABLE_LEGACY_INPUT_MANAGER
                true;
#else
                false;
#endif
            bool hasInputSystem =
#if ENABLE_INPUT_SYSTEM
                true;
#else
                false;
#endif

            switch (expected)
            {
                case "legacy":
                    Assert.IsTrue(hasLegacy, "Legacy fixture 应定义 ENABLE_LEGACY_INPUT_MANAGER");
                    Assert.IsFalse(hasInputSystem, "Legacy fixture 不应定义 ENABLE_INPUT_SYSTEM");
                    break;
                case "inputsystem":
                    Assert.IsFalse(hasLegacy, "InputSystem fixture 不应定义 ENABLE_LEGACY_INPUT_MANAGER");
                    Assert.IsTrue(hasInputSystem, "InputSystem fixture 应定义 ENABLE_INPUT_SYSTEM");
                    break;
                case "both":
                    Assert.IsTrue(hasLegacy, "Both fixture 应定义 ENABLE_LEGACY_INPUT_MANAGER");
                    Assert.IsTrue(hasInputSystem, "Both fixture 应定义 ENABLE_INPUT_SYSTEM");
                    break;
                default:
                    Assert.Fail($"未知 fixture 输入模式：{expected}（期望 legacy|inputsystem|both）");
                    break;
            }
        }
    }
}
