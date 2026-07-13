using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;

namespace Mk.UnityAgentBridge.Editor.Routing
{
    /// <summary>
    /// 候选 Runtime 持有的实例级服务注册表：Adapter 在 RegisterServices 阶段 <see cref="Add{T}"/> 登记
    /// 服务实现与优先级；Module/handler 通过 <see cref="TryGet{T}"/> / <see cref="GetAll{T}"/> 解析。
    /// 排序规则：优先级降序，其次类型全名升序（确定性排序，便于测试断言）。
    /// <see cref="TryGet{T}"/> 命中最高优先级存在多实现时视为单选冲突，抛
    /// <see cref="BridgeServiceConflictException"/>，由 Host 装配阶段捕获回滚。
    /// 不是静态全局表——每次事务装配都新建一份，避免污染当前 active runtime。
    /// </summary>
    public sealed class BridgeServiceRegistry : IBridgeServiceRegistry
    {
        private sealed class Entry
        {
            public object Service;
            public int Priority;
            public string TypeName;
            public int SequenceIndex;
        }

        private readonly List<Entry> entries = new List<Entry>();
        private int sequenceCounter;

        public void Add<T>(T service, int priority) where T : class
        {
            if (service == null)
            {
                throw new ArgumentNullException(nameof(service));
            }

            entries.Add(new Entry
            {
                Service = service,
                Priority = priority,
                TypeName = service.GetType().FullName ?? string.Empty,
                SequenceIndex = sequenceCounter++
            });
        }

        public bool TryGet<T>(out T service) where T : class
        {
            List<T> ordered = CollectSorted<T>();
            if (ordered.Count == 0)
            {
                service = null;
                return false;
            }

            if (ordered.Count > 1 && SharesTopPriority<T>())
            {
                throw new BridgeServiceConflictException(
                    $"服务类型 {typeof(T).FullName} 存在多个最高优先级实现，无法唯一选择");
            }

            service = ordered[0];
            return true;
        }

        public IReadOnlyList<T> GetAll<T>() where T : class
        {
            return CollectSorted<T>();
        }

        /// <summary>装配阶段收集生命周期用：返回已登记的全部服务实例（按引用去重，保持登记顺序）。</summary>
        public IReadOnlyList<object> AllServiceInstances()
        {
            List<object> result = new List<object>();
            HashSet<object> seen = new HashSet<object>();
            foreach (Entry entry in entries)
            {
                if (seen.Add(entry.Service))
                {
                    result.Add(entry.Service);
                }
            }

            return result;
        }

        private List<T> CollectSorted<T>() where T : class
        {
            List<Entry> matched = new List<Entry>();
            foreach (Entry entry in entries)
            {
                if (entry.Service is T)
                {
                    matched.Add(entry);
                }
            }

            matched.Sort(CompareEntries);

            List<T> result = new List<T>(matched.Count);
            foreach (Entry entry in matched)
            {
                result.Add((T)entry.Service);
            }

            return result;
        }

        private bool SharesTopPriority<T>() where T : class
        {
            List<Entry> matched = new List<Entry>();
            foreach (Entry entry in entries)
            {
                if (entry.Service is T)
                {
                    matched.Add(entry);
                }
            }

            if (matched.Count < 2)
            {
                return false;
            }

            matched.Sort(CompareEntries);
            return matched[0].Priority == matched[1].Priority;
        }

        private static int CompareEntries(Entry a, Entry b)
        {
            if (a.Priority != b.Priority)
            {
                // 优先级降序。
                return b.Priority.CompareTo(a.Priority);
            }

            int byType = string.CompareOrdinal(a.TypeName, b.TypeName);
            if (byType != 0)
            {
                return byType;
            }

            // 类型全名相同（同一类型多实例）时用登记顺序稳定兜底。
            return a.SequenceIndex.CompareTo(b.SequenceIndex);
        }
    }

    /// <summary>服务单选冲突：同一契约类型存在多个并列最高优先级实现时抛出。</summary>
    public sealed class BridgeServiceConflictException : Exception
    {
        public BridgeServiceConflictException(string message) : base(message)
        {
        }
    }
}
