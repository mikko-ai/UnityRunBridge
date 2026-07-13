using System;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Routing
{
    /// <summary>
    /// RouteTable 是全局静态注册表，生产路由（BridgeServer 静态构造函数注册）与测试共享同一份状态。
    /// 测试用带随机后缀的路径避免与生产路由或彼此冲突，并在结束时自行 Unregister，
    /// 不调用 RouteTable.Reset()（那会清空正在运行的 Bridge 的全部路由）。
    /// </summary>
    public sealed class RouteTableTests
    {
        [Test]
        public void Register_ThenResolve_ExactMatch()
        {
            string path = UniquePath("exact");
            RouteTable.Register("GET", path, ctx => "ok");
            try
            {
                RouteHandler handler = RouteTable.Resolve("GET", path, out string pathParam);
                Assert.IsNotNull(handler);
                Assert.IsNull(pathParam);
                Assert.AreEqual("ok", handler(null));
            }
            finally
            {
                RouteTable.Unregister("GET", path);
            }
        }

        [Test]
        public void Resolve_IsCaseInsensitiveOnMethodAndPath()
        {
            string path = UniquePath("CaseTest");
            RouteTable.Register("get", path.ToUpperInvariant(), ctx => "ok");
            try
            {
                RouteHandler handler = RouteTable.Resolve("GET", path.ToLowerInvariant(), out _);
                Assert.IsNotNull(handler);
            }
            finally
            {
                RouteTable.Unregister("GET", path);
            }
        }

        [Test]
        public void Resolve_TrailingParamSegment_CapturesValue()
        {
            string prefix = UniquePath("jobs");
            string pattern = $"{prefix}/{{id}}";
            RouteTable.Register("GET", pattern, ctx => "ok");
            try
            {
                RouteHandler handler = RouteTable.Resolve("GET", $"{prefix}/job-123", out string pathParam);
                Assert.IsNotNull(handler);
                Assert.AreEqual("job-123", pathParam);
            }
            finally
            {
                RouteTable.Unregister("GET", pattern);
            }
        }

        [Test]
        public void Resolve_WrongSegmentCount_DoesNotMatch()
        {
            string prefix = UniquePath("jobs2");
            string pattern = $"{prefix}/{{id}}";
            RouteTable.Register("GET", pattern, ctx => "ok");
            try
            {
                RouteHandler handler = RouteTable.Resolve("GET", $"{prefix}/a/b", out _);
                Assert.IsNull(handler);
            }
            finally
            {
                RouteTable.Unregister("GET", pattern);
            }
        }

        [Test]
        public void Resolve_UnknownRoute_ReturnsNull()
        {
            RouteHandler handler = RouteTable.Resolve("GET", UniquePath("does-not-exist"), out _);
            Assert.IsNull(handler);
        }

        [Test]
        public void Register_DuplicatePattern_Throws()
        {
            string path = UniquePath("dup");
            RouteTable.Register("POST", path, ctx => "ok");
            try
            {
                Assert.Throws<InvalidOperationException>(() => RouteTable.Register("POST", path, ctx => "ok2"));
            }
            finally
            {
                RouteTable.Unregister("POST", path);
            }
        }

        [Test]
        public void ListRoutes_IncludesRegisteredRoute()
        {
            string path = UniquePath("listed");
            RouteTable.Register("GET", path, ctx => "ok");
            try
            {
                var routes = RouteTable.ListRoutes();
                bool found = false;
                foreach (var route in routes)
                {
                    if (route.Method == "GET" && route.Path == path)
                    {
                        found = true;
                        break;
                    }
                }

                Assert.IsTrue(found);
            }
            finally
            {
                RouteTable.Unregister("GET", path);
            }
        }

        [Test]
        public void Unregister_UnknownRoute_ReturnsFalse()
        {
            Assert.IsFalse(RouteTable.Unregister("GET", UniquePath("never-registered")));
        }

        private static string UniquePath(string label)
        {
            return $"__test__/{label}-{Guid.NewGuid():N}";
        }
    }
}
