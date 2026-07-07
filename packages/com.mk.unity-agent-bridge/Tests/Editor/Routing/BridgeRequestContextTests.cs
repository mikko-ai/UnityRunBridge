using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Routing
{
    public sealed class BridgeRequestContextTests
    {
        [Test]
        public void ParseQuery_EmptyOrNull_ReturnsEmptyDictionary()
        {
            Assert.AreEqual(0, BridgeRequestContext.ParseQuery(null).Count);
            Assert.AreEqual(0, BridgeRequestContext.ParseQuery(string.Empty).Count);
            Assert.AreEqual(0, BridgeRequestContext.ParseQuery("?").Count);
        }

        [Test]
        public void ParseQuery_ParsesMultiplePairs()
        {
            Dictionary<string, string> result = BridgeRequestContext.ParseQuery("?a=1&b=two&c=");
            Assert.AreEqual("1", result["a"]);
            Assert.AreEqual("two", result["b"]);
            Assert.AreEqual(string.Empty, result["c"]);
        }

        [Test]
        public void ParseQuery_KeyIsLowercased()
        {
            Dictionary<string, string> result = BridgeRequestContext.ParseQuery("?Name=Value");
            Assert.IsTrue(result.ContainsKey("name"));
            Assert.AreEqual("Value", result["name"]);
        }

        [Test]
        public void ParseQuery_UrlDecodesValues()
        {
            Dictionary<string, string> result = BridgeRequestContext.ParseQuery("?path=Main%2FShopWindow%2FBuyButton&text=a%20b");
            Assert.AreEqual("Main/ShopWindow/BuyButton", result["path"]);
            Assert.AreEqual("a b", result["text"]);
        }

        [Test]
        public void ParseQuery_FlagWithoutEquals_BecomesEmptyString()
        {
            Dictionary<string, string> result = BridgeRequestContext.ParseQuery("?countOnly");
            Assert.IsTrue(result.ContainsKey("countonly"));
            Assert.AreEqual(string.Empty, result["countonly"]);
        }
    }
}
