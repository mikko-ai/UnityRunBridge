using System;

namespace Mk.UnityAgentBridge.Editor.Contracts
{
    /// <summary>标记一个 Adapter 生产类型，供 Host 通过 TypeCache 显式发现。</summary>
    [AttributeUsage(AttributeTargets.Class, Inherited = false)]
    public sealed class BridgeAdapterAttribute : Attribute
    {
    }

    /// <summary>标记一个 capability Module 生产类型，供 Host 通过 TypeCache 显式发现。</summary>
    [AttributeUsage(AttributeTargets.Class, Inherited = false)]
    public sealed class BridgeModuleAttribute : Attribute
    {
    }

    /// <summary>
    /// 标记一个程序集参与生产发现。只有同时带该 assembly marker 的程序集里的
    /// [BridgeAdapter]/[BridgeModule] 类型才会被 Host 采纳；测试程序集不加该标记，
    /// 从而把测试 Fake 排除在生产装配之外。
    /// </summary>
    [AttributeUsage(AttributeTargets.Assembly, Inherited = false)]
    public sealed class BridgeDiscoveryAssemblyAttribute : Attribute
    {
    }
}
