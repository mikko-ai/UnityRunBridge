using System;
using System.Collections.Generic;

namespace Mk.UnityAgentBridge.Editor.Routing
{
    internal delegate object RouteHandler(BridgeRequestContext context);

    /// <summary>
    /// 显式路由注册表：新增 Controller 通过 <see cref="Register"/> 登记路由，不再修改
    /// BridgeServer.Route() 的 if/else 链。匹配规则：精确匹配（小写、去首尾 '/'）
    /// + 支持单段尾参数模式（如 "jobs/{id}"，取出值放入 <see cref="BridgeRequestContext.PathParam"/>）。
    /// 不做通用正则路由。
    ///
    /// 生命周期：静态字段随 domain reload 清空，因此每次 reload 后 BridgeServer 的静态构造函数
    /// 必须重新调用所有 Controller 的 RegisterRoutes()（见 BridgeServer.RegisterAllRoutes）。
    /// </summary>
    internal static class RouteTable
    {
        private sealed class RouteEntry
        {
            public string Method;
            public string RawPattern;
            public string[] Segments;
            public RouteHandler Handler;
        }

        private static readonly List<RouteEntry> Routes = new List<RouteEntry>();

        public static void Reset()
        {
            Routes.Clear();
        }

        public static void Register(string method, string pathPattern, RouteHandler handler)
        {
            if (handler == null)
            {
                throw new ArgumentNullException(nameof(handler));
            }

            string normalizedMethod = NormalizeMethod(method);
            string normalizedPattern = NormalizePath(pathPattern);

            if (Routes.Exists(r => r.Method == normalizedMethod && r.RawPattern == normalizedPattern))
            {
                throw new InvalidOperationException($"路由重复注册: {normalizedMethod} /{normalizedPattern}");
            }

            Routes.Add(new RouteEntry
            {
                Method = normalizedMethod,
                RawPattern = normalizedPattern,
                Segments = Split(normalizedPattern),
                Handler = handler
            });
        }

        public static bool Unregister(string method, string pathPattern)
        {
            string normalizedMethod = NormalizeMethod(method);
            string normalizedPattern = NormalizePath(pathPattern);
            return Routes.RemoveAll(r => r.Method == normalizedMethod && r.RawPattern == normalizedPattern) > 0;
        }

        public static RouteHandler Resolve(string method, string path, out string pathParam)
        {
            pathParam = null;
            string normalizedMethod = NormalizeMethod(method);
            string[] pathSegments = Split(NormalizePath(path));

            foreach (RouteEntry route in Routes)
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

        public static IReadOnlyList<(string Method, string Path)> ListRoutes()
        {
            List<(string, string)> list = new List<(string, string)>();
            foreach (RouteEntry route in Routes)
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
