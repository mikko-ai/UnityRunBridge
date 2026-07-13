using System.Diagnostics;
using Mk.UnityAgentBridge.Editor.Routing;

namespace Mk.UnityAgentBridge.Editor.Hierarchy
{
    public static class Pagination
    {
        public const int DefaultPageSize = 50;
        public const int MaxPageSize = 500;

        public static int ResolvePageSize(BridgeRequestContext ctx)
        {
            int size = ctx.GetQueryInt("pageSize", DefaultPageSize);
            return size <= 0 ? DefaultPageSize : System.Math.Min(size, MaxPageSize);
        }

        public static bool TryParseCursor(string cursor, out int offset)
        {
            if (string.IsNullOrEmpty(cursor))
            {
                offset = 0;
                return true;
            }

            return int.TryParse(cursor, out offset) && offset >= 0;
        }
    }

    /// <summary>
    /// 求值预算：单次请求最多访问 <see cref="MaxNodesVisited"/> 个节点或耗时
    /// <see cref="MaxMillis"/> 毫秒（先到为准），超出即停止遍历并标记 truncated。
    /// </summary>
    public sealed class EvalBudget
    {
        public const int MaxNodesVisited = 5000;
        public const long MaxMillis = 50;

        private readonly Stopwatch stopwatch = Stopwatch.StartNew();
        private int visited;

        public bool TryConsume()
        {
            visited++;
            return visited <= MaxNodesVisited && stopwatch.ElapsedMilliseconds <= MaxMillis;
        }
    }
}
