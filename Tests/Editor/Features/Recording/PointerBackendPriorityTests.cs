using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Recording;
using NUnit.Framework;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Tests.Recording
{
    /// <summary>验证 Both 模式下只选 Priority 最高的 pointer backend。</summary>
    public sealed class PointerBackendPriorityTests
    {
        private sealed class FakePointer : IPointerInputBackend
        {
            public int Priority { get; }
            public string Name { get; }

            public FakePointer(string name, int priority)
            {
                Name = name;
                Priority = priority;
            }

            public bool TryGetPointerDown(out Vector2 position)
            {
                position = default;
                return false;
            }

            public bool TryGetPointerUp(out Vector2 position)
            {
                position = default;
                return false;
            }
        }

        private sealed class FakeRegistry : IBridgeServiceResolver
        {
            private readonly List<object> services = new List<object>();

            public void Add(object service) => services.Add(service);

            public bool TryGet<T>(out T service) where T : class
            {
                IReadOnlyList<T> all = GetAll<T>();
                if (all.Count == 0)
                {
                    service = null;
                    return false;
                }

                service = all[0];
                return true;
            }

            public IReadOnlyList<T> GetAll<T>() where T : class
            {
                List<(T Service, int Priority, string TypeName)> matched = new List<(T, int, string)>();
                foreach (object item in services)
                {
                    if (item is T typed && item is IPointerInputBackend pointer)
                    {
                        matched.Add((typed, pointer.Priority, item.GetType().FullName ?? string.Empty));
                    }
                    else if (item is T onlyTyped)
                    {
                        matched.Add((onlyTyped, 0, item.GetType().FullName ?? string.Empty));
                    }
                }

                matched.Sort((a, b) =>
                {
                    if (a.Priority != b.Priority)
                    {
                        return b.Priority.CompareTo(a.Priority);
                    }

                    return string.CompareOrdinal(a.TypeName, b.TypeName);
                });

                List<T> result = new List<T>(matched.Count);
                foreach ((T service, int _, string _) in matched)
                {
                    result.Add(service);
                }

                return result;
            }
        }

        [Test]
        public void TrySelectPointerBackend_BothRegistered_SelectsHigherPriorityOnly()
        {
            FakeRegistry registry = new FakeRegistry();
            FakePointer legacy = new FakePointer("legacy", 100);
            FakePointer inputSystem = new FakePointer("inputSystem", 200);
            registry.Add(legacy);
            registry.Add(inputSystem);

            Assert.IsTrue(RecordingListener.TrySelectPointerBackend(registry, out IPointerInputBackend selected));
            Assert.AreSame(inputSystem, selected);
            Assert.AreEqual(200, selected.Priority);
        }

        [Test]
        public void TrySelectPointerBackend_Empty_ReturnsFalse()
        {
            FakeRegistry registry = new FakeRegistry();
            Assert.IsFalse(RecordingListener.TrySelectPointerBackend(registry, out IPointerInputBackend selected));
            Assert.IsNull(selected);
        }
    }
}
