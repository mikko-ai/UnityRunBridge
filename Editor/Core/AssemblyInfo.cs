using System.Runtime.CompilerServices;

// Core 实现细节保持 internal，仅对需要 ForTests / JobManager 测试钩子的程序集开放。
[assembly: InternalsVisibleTo("Mk.UnityAgentBridge.Editor.Tests.Core")]
[assembly: InternalsVisibleTo("Mk.UnityAgentBridge.Editor.Features.Tests")]
[assembly: InternalsVisibleTo("Mk.UnityAgentBridge.Editor.Tests.UGUI")]
[assembly: InternalsVisibleTo("Mk.UnityAgentBridge.Editor.Tests.UGUI.EditorIntegration")]
