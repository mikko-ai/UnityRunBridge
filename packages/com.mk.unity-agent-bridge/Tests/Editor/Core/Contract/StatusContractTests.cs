using System;
using System.Collections.Generic;
using System.Reflection;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Contract
{
    /// <summary>
    /// 冻结 GET /status 的字段形状与 editorState 可取值，防止重构破坏 CLI 收敛逻辑。
    /// </summary>
    public sealed class StatusContractTests
    {
        private static readonly string[] RequiredStatusFields =
        {
            "ok",
            "code",
            "message",
            "bridgeVersion",
            "unityVersion",
            "editorState",
            "isPlaying",
            "isPaused",
            "isCompiling",
            "isUpdating",
            "willEnterPlayMode",
            "activeScenePath",
            "compilationSucceeded",
            "compilationFinishedAt",
            "compilationErrors",
            "hasActiveSession",
            "sessionId",
            "sessionPath",
            "logPath",
        };

        private static readonly string[] AllowedEditorStates =
        {
            "compiling",
            "updating",
            "paused",
            "exitingPlay",
            "playing",
            "enteringPlay",
            "idle",
        };

        [Test]
        public void BridgeStatusResponse_ExposesRequiredContractFields()
        {
            HashSet<string> fields = new HashSet<string>(StringComparer.Ordinal);
            foreach (FieldInfo field in typeof(BridgeStatusResponse).GetFields(BindingFlags.Instance | BindingFlags.Public))
            {
                fields.Add(field.Name);
            }

            foreach (string required in RequiredStatusFields)
            {
                Assert.IsTrue(fields.Contains(required), $"缺少 status 字段：{required}");
            }
        }

        [Test]
        public void GetStatus_ReturnsAllRequiredContractValues()
        {
            BridgeStatusResponse status = EditorStateProvider.GetStatus();

            Assert.IsTrue(status.ok);
            Assert.AreEqual("ok", status.code);
            Assert.IsNotNull(status.message);
            Assert.AreEqual(BridgeConfig.Version, status.bridgeVersion);
            Assert.IsFalse(string.IsNullOrEmpty(status.unityVersion));
            Assert.IsNotNull(status.activeScenePath);
            Assert.IsNotNull(status.compilationErrors);
            CollectionAssert.Contains(AllowedEditorStates, status.editorState);
        }

        [Test]
        public void DeriveState_OnlyProducesAllowedEditorStates()
        {
            bool[] flags = { false, true };
            HashSet<string> observed = new HashSet<string>(StringComparer.Ordinal);

            foreach (bool isCompiling in flags)
            {
                foreach (bool isUpdating in flags)
                {
                    foreach (bool isPlaying in flags)
                    {
                        foreach (bool isPaused in flags)
                        {
                            foreach (bool willChangePlaymode in flags)
                            {
                                string state = EditorStateProvider.DeriveState(
                                    isCompiling,
                                    isUpdating,
                                    isPlaying,
                                    isPaused,
                                    willChangePlaymode);
                                observed.Add(state);
                                CollectionAssert.Contains(AllowedEditorStates, state);
                            }
                        }
                    }
                }
            }

            CollectionAssert.AreEquivalent(AllowedEditorStates, observed);
        }
    }
}
