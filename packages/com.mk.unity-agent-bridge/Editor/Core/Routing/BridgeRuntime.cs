namespace Mk.UnityAgentBridge.Editor.Routing
{
    /// <summary>
    /// 一次事务装配的产物：持有本次装配的服务注册表、路由表、capability 集合。
    /// Host 在候选实例上完成注册与校验，成功后调用 <see cref="Publish"/> 把它设为 active，
    /// 之后 HTTP pipeline 与 GET /capabilities 只读同一份 active runtime 的不可变快照。
    /// 静态 <see cref="RouteTable"/> / <see cref="CapabilityRegistry"/> 门面转发到 active，
    /// 兼容既有 Controller 测试与契约测试；候选在 Publish 前绝不污染 active。
    /// </summary>
    public sealed class BridgeRuntime
    {
        private static BridgeRuntime active;

        public BridgeServiceRegistry Services { get; } = new BridgeServiceRegistry();
        public InstanceRouteTable Routes { get; } = new InstanceRouteTable();
        public InstanceCapabilityRegistry Capabilities { get; } = new InstanceCapabilityRegistry();

        /// <summary>当前对外生效的 runtime；Host 尚未发布时为 null。</summary>
        public static BridgeRuntime Active => active;

        /// <summary>成功装配并 Start 生命周期后，由 Host 发布为 active。</summary>
        public static void Publish(BridgeRuntime runtime)
        {
            active = runtime;
        }

        /// <summary>装配失败回滚时清空对外快照，避免半装配状态泄漏。</summary>
        public static void ClearActive()
        {
            active = null;
        }
    }
}
