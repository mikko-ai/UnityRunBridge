using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Adapters.LegacyInput.Tests
{
    /// <summary>Legacy Input Adapter：指针后端 Priority=100。</summary>
    public sealed class LegacyPointerBackendTests
    {
        [Test]
        public void RegisterServices_ExposesPointerBackendWithPriority100()
        {
            BridgeRuntime runtime = new BridgeRuntime();
            new LegacyInputBridgeAdapter().RegisterServices(runtime.Services);

            Assert.IsTrue(runtime.Services.TryGet(out IPointerInputBackend backend));
            Assert.AreEqual(100, backend.Priority);

            // 无真实按下时返回 false，但不抛异常。
            Assert.IsFalse(backend.TryGetPointerDown(out Vector2 down));
            Assert.AreEqual(default(Vector2), down);
            Assert.IsFalse(backend.TryGetPointerUp(out Vector2 up));
            Assert.AreEqual(default(Vector2), up);
        }
    }
}
