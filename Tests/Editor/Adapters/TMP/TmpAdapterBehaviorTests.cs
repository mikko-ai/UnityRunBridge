using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using TMPro;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Adapters.TMP.Tests
{
    /// <summary>TMP Adapter 最小行为测试（仅在安装 TMP 的 fixture 中编译）。</summary>
    public sealed class TmpAdapterBehaviorTests
    {
        [Test]
        public void TextAdapter_TryGetText_FromTmpText()
        {
            BridgeRuntime runtime = new BridgeRuntime();
            new TmpBridgeAdapter().RegisterServices(runtime.Services);

            GameObject go = new GameObject("TmpText");
            try
            {
                TextMeshProUGUI tmp = go.AddComponent<TextMeshProUGUI>();
                tmp.text = "TMP内容";

                bool found = false;
                string value = null;
                foreach (ITextControlAdapter adapter in runtime.Services.GetAll<ITextControlAdapter>())
                {
                    if (adapter.TryGetText(go, out value))
                    {
                        found = true;
                        break;
                    }
                }

                Assert.IsTrue(found);
                Assert.AreEqual("TMP内容", value);
            }
            finally
            {
                Object.DestroyImmediate(go);
            }
        }
    }
}
