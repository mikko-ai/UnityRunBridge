using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Adapters.InputSystem.Tests
{
    /// <summary>Input System Adapter：指针后端 Priority=200（高于 Legacy）。</summary>
    public sealed class InputSystemPointerBackendTests
    {
        [Test]
        public void RegisterServices_ExposesPointerBackendWithPriority200()
        {
            BridgeRuntime runtime = new BridgeRuntime();
            new InputSystemBridgeAdapter().RegisterServices(runtime.Services);

            Assert.IsTrue(runtime.Services.TryGet(out IPointerInputBackend backend));
            Assert.AreEqual(200, backend.Priority);
            Assert.IsFalse(backend.TryGetPointerDown(out Vector2 _));
            Assert.IsFalse(backend.TryGetPointerUp(out Vector2 _));
        }
    }
}
