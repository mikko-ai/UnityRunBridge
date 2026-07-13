using System.Runtime.CompilerServices;

// Host 实现细节保持 internal，仅对 Host 自己的测试程序集开放。
[assembly: InternalsVisibleTo("Mk.UnityAgentBridge.Editor.Tests.Host")]

// 注意：Host 刻意不加 [assembly: BridgeDiscoveryAssembly]。
// 生产发现只采纳带该 assembly marker 的程序集里的 [BridgeModule]/[BridgeAdapter]，
// Host 只是 composition root，不提供 Feature/Adapter 生产类型。
