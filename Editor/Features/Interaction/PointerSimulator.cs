using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Interaction
{
    /// <summary>
    /// Features 侧点击入口：转发到 <c>IInteractionBackend</c>，保留 <c>ClickResult</c> 形状供 Controller / 测试使用。
    /// </summary>
    internal static class PointerSimulator
    {
        public sealed class ClickResult
        {
            public bool Ok;
            public string ErrorCode;
            public string ErrorMessage;
            public GameObject Clicked;
            public GameObject RaycastHit;
            public List<string> Events;
            public bool Forced;

            public static ClickResult Fail(string code, string message)
            {
                return new ClickResult { Ok = false, ErrorCode = code, ErrorMessage = message };
            }

            public static ClickResult Success(GameObject clicked, GameObject raycastHit, List<string> events, bool forced)
            {
                return new ClickResult { Ok = true, Clicked = clicked, RaycastHit = raycastHit, Events = events, Forced = forced };
            }
        }

        public static ClickResult SimulateClick(GameObject target, bool force, IBridgeServiceResolver services = null)
        {
            services = BridgeServices.Current(services);
            if (services == null || !services.TryGet(out IInteractionBackend backend))
            {
                return ClickResult.Fail("no_interaction_backend", "未注册 IInteractionBackend（通常需要 UGUI Adapter）");
            }

            InteractionOperationResult result = backend.Click(target, force);
            if (!result.Ok)
            {
                ClickResult failure = ClickResult.Fail(result.ErrorCode, result.ErrorMessage);
                failure.RaycastHit = result.RaycastHit;
                return failure;
            }

            return ClickResult.Success(
                result.Clicked,
                result.RaycastHit,
                result.Events ?? new List<string>(),
                result.Forced);
        }
    }
}
