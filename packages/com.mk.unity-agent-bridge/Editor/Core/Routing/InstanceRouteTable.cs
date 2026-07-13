using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;

namespace Mk.UnityAgentBridge.Editor.Routing
{
    /// <summary>
    /// 候选/active Runtime 持有的实例级路由表，实现 <see cref="IRouteRegistrar"/>：Module 通过
    /// <see cref="Map"/> 显式登记 method+path→handler。匹配规则与旧静态 RouteTable 一致：
    /// 精确匹配（小写、去首尾 '/'）+ 支持单段尾参数模式（如 "jobs/{id}"）。
    /// 重复注册抛 <see cref="InvalidOperationException"/>，由 Host 装配阶段捕获回滚。
    /// 不再是静态全局表——每次事务装配新建一份，成功后才作为 active 发布。
    /// </summary>
    public sealed class InstanceRouteTable : IRouteRegistrar
    {
        private sealed class RouteEntry
        {
            public string Method;
            public string RawPattern;
            public string[] Segments;
            public BridgeRouteHandler Handler;
        }

        private readonly List<RouteEntry> routes = new List<RouteEntry>();

        public void Map(string method, string pathPattern, BridgeRouteHandler handler)
        {
            if (handler == null)
            {
                throw new ArgumentNullException(nameof(handler));
            }

            string normalizedMethod = NormalizeMethod(method);
            string normalizedPattern = NormalizePath(pathPattern);

            if (routes.Exists(r => r.Method == normalizedMethod && r.RawPattern == normalizedPattern))
            {
                throw new InvalidOperationException($"路由重复注册: {normalizedMethod} /{normalizedPattern}");
            }

            routes.Add(new RouteEntry
            {
                Method = normalizedMethod,
                RawPattern = normalizedPattern,
                Segments = Split(normalizedPattern),
                Handler = handler
            });
        }

        public bool Unregister(string method, string pathPattern)
        {
            string normalizedMethod = NormalizeMethod(method);
            string normalizedPattern = NormalizePath(pathPattern);
            return routes.RemoveAll(r => r.Method == normalizedMethod && r.RawPattern == normalizedPattern) > 0;
        }

        public void Clear()
        {
            routes.Clear();
        }

        public BridgeRouteHandler Resolve(string method, string path, out string pathParam)
        {
            pathParam = null;
            string normalizedMethod = NormalizeMethod(method);
            string[] pathSegments = Split(NormalizePath(path));

            foreach (RouteEntry route in routes)
            {
                if (route.Method != normalizedMethod || route.Segments.Length != pathSegments.Length)
                {
                    continue;
                }

                string capturedParam = null;
                bool matched = true;
                for (int i = 0; i < route.Segments.Length; i++)
                {
                    string routeSegment = route.Segments[i];
                    if (IsParamSegment(routeSegment))
                    {
                        capturedParam = pathSegments[i];
                        continue;
                    }

                    if (!string.Equals(routeSegment, pathSegments[i], StringComparison.Ordinal))
                    {
                        matched = false;
                        break;
                    }
                }

                if (matched)
                {
                    pathParam = capturedParam;
                    return route.Handler;
                }
            }

            return null;
        }

        public IReadOnlyList<(string Method, string Path)> ListRoutes()
        {
            List<(string, string)> list = new List<(string, string)>();
            foreach (RouteEntry route in routes)
            {
                list.Add((route.Method, route.RawPattern));
            }

            return list;
        }

        private static bool IsParamSegment(string segment)
        {
            return segment.Length >= 2 && segment[0] == '{' && segment[segment.Length - 1] == '}';
        }

        private static string NormalizeMethod(string method)
        {
            return (method ?? string.Empty).Trim().ToUpperInvariant();
        }

        private static string NormalizePath(string pathPattern)
        {
            return (pathPattern ?? string.Empty).Trim('/').ToLowerInvariant();
        }

        private static string[] Split(string normalizedPath)
        {
            return normalizedPath.Length == 0 ? Array.Empty<string>() : normalizedPath.Split('/');
        }
    }
}
