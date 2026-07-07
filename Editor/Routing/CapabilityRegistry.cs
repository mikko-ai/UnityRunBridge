using System;
using System.Collections.Generic;
using System.Linq;

namespace Mk.UnityAgentBridge.Editor.Routing
{
    /// <summary>
    /// 各 Controller 在 RegisterRoutes() 中调用 <see cref="Declare"/> 声明自己提供的能力标签，
    /// GET /capabilities 据此告知 CLI 当前 Bridge 版本支持哪些功能，供其做兼容降级。
    /// "core" 恒存在，代表握手 / status / play-stop 等基础能力。
    /// </summary>
    internal static class CapabilityRegistry
    {
        private static readonly HashSet<string> Capabilities = new HashSet<string>(StringComparer.Ordinal) { "core" };

        public static void Reset()
        {
            Capabilities.Clear();
            Capabilities.Add("core");
        }

        public static void Declare(string capability)
        {
            if (!string.IsNullOrWhiteSpace(capability))
            {
                Capabilities.Add(capability);
            }
        }

        public static IReadOnlyList<string> All()
        {
            List<string> sorted = Capabilities.ToList();
            sorted.Sort(StringComparer.Ordinal);
            return sorted;
        }
    }
}
