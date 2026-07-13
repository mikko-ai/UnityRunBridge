using System.Runtime.CompilerServices;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Jobs;

namespace Mk.UnityAgentBridge.Editor.Lifecycle
{
    /// <summary>
    /// Core 基础设施生命周期：把原先散落在各静态类上的 [InitializeOnLoad] 收敛到 Host composition root，
    /// 由 Host 在 Start 时统一驱动。Start() 强制运行 JobManager / TempObjectRegistry / CompilationTracker
    /// 的静态构造函数完成事件订阅（timeout 轮询、domain reload / play mode / quit 清理、编译结果跟踪），
    /// 时机与原先的 InitializeOnLoad 一致（Editor 载入 / 每次 domain reload 后）。
    ///
    /// 静态类的事件订阅不做显式反订阅（与迁移前行为一致），因此 Stop/Dispose 为空实现——
    /// 这些订阅本就伴随 Editor 会话存活，domain reload 会连带清空静态订阅、下次 Start 重新建立。
    /// </summary>
    public sealed class CoreServicesLifecycle : IBridgeLifecycle
    {
        public void Start()
        {
            EnsureInitialized(typeof(TempObjectRegistry));
            EnsureInitialized(typeof(JobManager));
            EnsureInitialized(typeof(CompilationTracker));
        }

        public void Stop()
        {
        }

        public void Dispose()
        {
        }

        private static void EnsureInitialized(System.Type type)
        {
            RuntimeHelpers.RunClassConstructor(type.TypeHandle);
        }
    }
}
