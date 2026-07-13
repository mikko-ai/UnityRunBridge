using System.IO;
using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;
using UnityEditor.Compilation;

namespace Mk.UnityAgentBridge.Editor.Tests
{
    /// <summary>
    /// 依赖守卫：Features / Host 不得引用可选包（UGUI / TMP / Input System）；
    /// Host 不得编译引用 Features / Adapters。
    /// </summary>
    public sealed class FeaturesHostAssemblyGuardTests
    {
        private static readonly string[] ForbiddenOptionalPackages =
        {
            "UnityEngine.UI",
            "Unity.TextMeshPro",
            "Unity.InputSystem",
        };

        [Test]
        public void FeaturesAsmdef_ReferencesOnlyCore_AndNoOptionalPackages()
        {
            AssertAsmdefReferences(
                "Mk.UnityAgentBridge.Editor.Features",
                expectedReferences: new[] { "Mk.UnityAgentBridge.Editor.Core" },
                forbidden: ForbiddenOptionalPackages);
        }

        [Test]
        public void HostAsmdef_ReferencesOnlyCore_AndNoFeaturesOrAdapters()
        {
            AssertAsmdefReferences(
                "Mk.UnityAgentBridge.Editor.Host",
                expectedReferences: new[] { "Mk.UnityAgentBridge.Editor.Core" },
                forbidden: new[]
                {
                    "Mk.UnityAgentBridge.Editor.Features",
                    "Mk.UnityAgentBridge.Editor.Adapters",
                    "UnityEngine.UI",
                    "Unity.TextMeshPro",
                    "Unity.InputSystem",
                });
        }

        [Test]
        public void BuildAsmdef_ReferencesOnlyCore()
        {
            AssertAsmdefReferences(
                "Mk.UnityAgentBridge.Editor.Build",
                expectedReferences: new[] { "Mk.UnityAgentBridge.Editor.Core" },
                forbidden: ForbiddenOptionalPackages);
        }

        private static void AssertAsmdefReferences(
            string assemblyName,
            string[] expectedReferences,
            string[] forbidden)
        {
            string asmdefPath = CompilationPipeline.GetAssemblyDefinitionFilePathFromAssemblyName(assemblyName);
            Assert.IsFalse(string.IsNullOrEmpty(asmdefPath), $"未能定位 {assemblyName} asmdef 路径");

            string json = File.ReadAllText(asmdefPath);
            JsonValue asmdef = JsonParser.Parse(json);
            Assert.IsTrue(asmdef.IsObject, $"{assemblyName} asmdef 应为 JSON 对象");

            JsonValue references = asmdef["references"];
            Assert.IsTrue(references.IsArray, $"{assemblyName} asmdef 的 references 应为数组");

            var actual = new System.Collections.Generic.List<string>();
            foreach (JsonValue item in references.Items)
            {
                actual.Add(item.AsString);
            }

            CollectionAssert.AreEquivalent(expectedReferences, actual, $"{assemblyName} references 不符合预期");

            foreach (string reference in actual)
            {
                foreach (string ban in forbidden)
                {
                    StringAssert.DoesNotContain(ban, reference, $"{assemblyName} 不应引用：{ban}");
                }
            }
        }
    }
}
