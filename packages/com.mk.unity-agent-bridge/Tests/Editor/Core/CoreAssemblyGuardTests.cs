using System.IO;
using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;
using UnityEditor.Compilation;

namespace Mk.UnityAgentBridge.Editor.Tests.Core
{
    /// <summary>
    /// 依赖守卫：Core 程序集不得引用任何可选包（UGUI / TMP / Input System）。
    /// 直接读取 Core.asmdef 的 references 断言，作为架构边界的硬门禁。
    /// </summary>
    public sealed class CoreAssemblyGuardTests
    {
        private const string CoreAssemblyName = "Mk.UnityAgentBridge.Editor.Core";

        private static readonly string[] ForbiddenReferences =
        {
            "UnityEngine.UI",
            "Unity.TextMeshPro",
            "Unity.InputSystem",
        };

        [Test]
        public void CoreAsmdef_ReferencesDoNotContainOptionalPackages()
        {
            string asmdefPath = CompilationPipeline.GetAssemblyDefinitionFilePathFromAssemblyName(CoreAssemblyName);
            Assert.IsFalse(string.IsNullOrEmpty(asmdefPath), "未能定位 Core asmdef 路径");

            string json = File.ReadAllText(asmdefPath);
            JsonValue asmdef = JsonParser.Parse(json);
            Assert.IsTrue(asmdef.IsObject, "Core asmdef 应为 JSON 对象");

            JsonValue references = asmdef["references"];
            Assert.IsTrue(references.IsArray, "Core asmdef 的 references 应为数组");

            foreach (JsonValue item in references.Items)
            {
                string reference = item.AsString;
                foreach (string forbidden in ForbiddenReferences)
                {
                    StringAssert.DoesNotContain(
                        forbidden,
                        reference,
                        $"Core asmdef 不应引用可选包：{forbidden}");
                }
            }
        }
    }
}
