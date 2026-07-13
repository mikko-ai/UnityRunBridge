using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Core
{
    /// <summary>
    /// 契约测试：具体的 <see cref="BridgeRequestContext"/> 必须实现 Core 契约
    /// <see cref="IBridgeRequestContext"/>，且各访问器语义与既有实现一致。
    /// </summary>
    public sealed class BridgeRequestContextContractTests
    {
        [Test]
        public void BridgeRequestContext_ImplementsIBridgeRequestContext()
        {
            IBridgeRequestContext ctx = BridgeRequestContext.ForTests(
                pathParam: "abc",
                rawBody: "{\"k\":1}",
                query: new Dictionary<string, string> { ["page"] = "2", ["flag"] = "true" });

            Assert.AreEqual("abc", ctx.PathParam);
            Assert.AreEqual("{\"k\":1}", ctx.RawBody);
            Assert.IsNotNull(ctx.Body);
            Assert.IsTrue(ctx.Body.IsObject);
            Assert.IsTrue(ctx.HasQuery("page"));
            Assert.AreEqual(2, ctx.GetQueryInt("page", 0));
            Assert.IsTrue(ctx.GetQueryBool("flag", false));
            Assert.AreEqual("fallback", ctx.GetQuery("missing", "fallback"));
            Assert.IsTrue(ctx.QueryParams.ContainsKey("page"));
        }

        [Test]
        public void BridgeRequestContext_EmptyBody_ReturnsNullBody()
        {
            IBridgeRequestContext ctx = BridgeRequestContext.ForTests(pathParam: "p");
            Assert.IsNull(ctx.Body);
        }
    }
}
