using System;

namespace Mk.UnityAgentBridge.Editor.Host
{
    /// <summary>
    /// 事务装配失败：重复路由、重复 capability、服务单选冲突、候选构造异常等都归一到此异常，
    /// 由 <see cref="BridgeServer"/> 捕获后执行回滚（逆序 Stop 已 Start 的、Dispose 全部候选、不发布 active）。
    /// </summary>
    internal sealed class BridgeCompositionException : Exception
    {
        public BridgeCompositionException(string message) : base(message)
        {
        }

        public BridgeCompositionException(string message, Exception innerException) : base(message, innerException)
        {
        }
    }
}
