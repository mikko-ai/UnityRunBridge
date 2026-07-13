using System;
using System.Collections.Generic;
using System.Linq;

namespace Mk.UnityAgentBridge.Editor.Routing
{
    /// <summary>
    /// 候选/active Runtime 持有的实例级 capability 集合：Module 装配时声明自己提供的能力标签，
    /// GET /capabilities 据此告知 CLI 当前 Bridge 支持哪些功能。<see cref="All"/> 使用 ordinal 排序，
    /// 与旧静态 CapabilityRegistry 输出顺序一致。"core" 不再预置，由 Core 能力模块显式声明。
    /// </summary>
    public sealed class InstanceCapabilityRegistry
    {
        private readonly HashSet<string> capabilities = new HashSet<string>(StringComparer.Ordinal);

        public void Declare(string capability)
        {
            if (!string.IsNullOrWhiteSpace(capability))
            {
                capabilities.Add(capability);
            }
        }

        public bool Contains(string capability)
        {
            return !string.IsNullOrWhiteSpace(capability) && capabilities.Contains(capability);
        }

        public void Clear()
        {
            capabilities.Clear();
        }

        public IReadOnlyList<string> All()
        {
            List<string> sorted = capabilities.ToList();
            sorted.Sort(StringComparer.Ordinal);
            return sorted;
        }
    }
}
