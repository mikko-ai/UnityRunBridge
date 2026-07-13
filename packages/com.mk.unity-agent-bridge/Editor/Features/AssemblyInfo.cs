using System.Runtime.CompilerServices;
using Mk.UnityAgentBridge.Editor.Contracts;

[assembly: BridgeDiscoveryAssembly]

// Features 实现细节保持 internal，仅对对应测试程序集开放。
[assembly: InternalsVisibleTo("Mk.UnityAgentBridge.Editor.Features.Tests")]
[assembly: InternalsVisibleTo("Mk.UnityAgentBridge.Editor.Tests.UGUI")]
[assembly: InternalsVisibleTo("Mk.UnityAgentBridge.Editor.Tests.UGUI.EditorIntegration")]
