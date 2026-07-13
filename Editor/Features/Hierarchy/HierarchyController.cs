using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Hierarchy
{
    internal static class HierarchyController
    {
        public static object Roots()
        {
            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            JsonValue scenes = JsonValue.NewArray();
            foreach (HierarchyScan.SceneRoots sceneRoots in HierarchyScan.GetAllScenesWithRoots())
            {
                JsonValue sceneJson = JsonValue.NewObject();
                sceneJson["scene"] = sceneRoots.SceneName;
                sceneJson["isLoaded"] = sceneRoots.IsLoaded;
                JsonValue roots = JsonValue.NewArray();
                foreach (Transform root in sceneRoots.Roots)
                {
                    roots.Add(NodeSerializer.BuildSummary(root));
                }

                sceneJson["roots"] = roots;
                scenes.Add(sceneJson);
            }

            response["scenes"] = scenes;
            return response;
        }

        public static object Tree(BridgeRequestContext ctx)
        {
            string identifier = ResolveIdentifier(ctx);
            if (identifier == null)
            {
                return BridgeResponse.Failure("invalid_argument", "path or instanceId is required");
            }

            NodePath.ResolveResult resolved = NodePath.Resolve(identifier, ctx.GetQuery("scene"));
            if (!resolved.Ok)
            {
                return BridgeResponse.Failure(resolved.ErrorCode, resolved.ErrorMessage);
            }

            int depth = ctx.GetQueryInt("depth", 3);
            int pageSize = Pagination.ResolvePageSize(ctx);
            if (!Pagination.TryParseCursor(ctx.GetQuery("cursor"), out int cursorOffset))
            {
                return BridgeResponse.Failure("stale_cursor", "cursor 无法解析");
            }

            List<Transform> visitedOrder = new List<Transform>();
            EvalBudget budget = new EvalBudget();
            bool budgetExhausted = !CollectBfs(resolved.Node, depth, budget, visitedOrder);

            int available = visitedOrder.Count - cursorOffset;
            int take = Math.Max(0, Math.Min(pageSize, available));
            JsonValue nodes = JsonValue.NewArray();
            for (int i = 0; i < take; i++)
            {
                nodes.Add(NodeSerializer.BuildSummary(visitedOrder[cursorOffset + i]));
            }

            bool truncated = budgetExhausted || cursorOffset + take < visitedOrder.Count;

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["root"] = NodePath.BuildPath(resolved.Node);
            response["nodes"] = nodes;
            response["totalVisited"] = visitedOrder.Count;
            response["truncated"] = truncated;
            response["nextCursor"] = truncated ? JsonValue.FromString((cursorOffset + take).ToString()) : JsonValue.Null;
            return response;
        }

        public static object Find(BridgeRequestContext ctx)
        {
            FindQueryResult parsed = FindQuery.Parse(ctx);
            if (!parsed.Ok)
            {
                return BridgeResponse.Failure(parsed.ErrorCode, parsed.ErrorMessage);
            }

            int pageSize = Pagination.ResolvePageSize(ctx);
            if (!Pagination.TryParseCursor(ctx.GetQuery("cursor"), out int cursorOffset))
            {
                return BridgeResponse.Failure("stale_cursor", "cursor 无法解析");
            }

            string sceneFilter = ctx.GetQuery("scene");
            EvalBudget budget = new EvalBudget();
            List<Transform> matches = new List<Transform>();
            bool budgetExhausted = !CollectMatches(parsed.Criteria, sceneFilter, budget, matches);

            if (parsed.Criteria.CountOnly)
            {
                JsonValue countResponse = JsonValue.NewObject();
                countResponse["ok"] = true;
                countResponse["matchedCount"] = matches.Count;
                countResponse["partial"] = budgetExhausted;
                countResponse["nextCursor"] = budgetExhausted ? JsonValue.FromString(matches.Count.ToString()) : JsonValue.Null;
                return countResponse;
            }

            if (parsed.Criteria.SortComponentType != null)
            {
                SortMatches(matches, parsed.Criteria);
            }

            int available = matches.Count - cursorOffset;
            int take = Math.Max(0, Math.Min(pageSize, available));
            JsonValue nodes = JsonValue.NewArray();
            for (int i = 0; i < take; i++)
            {
                nodes.Add(NodeSerializer.BuildSummary(matches[cursorOffset + i]));
            }

            bool truncated = budgetExhausted || cursorOffset + take < matches.Count;

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["matchedCount"] = matches.Count;
            response["nodes"] = nodes;
            response["truncated"] = truncated;
            response["nextCursor"] = truncated ? JsonValue.FromString((cursorOffset + take).ToString()) : JsonValue.Null;
            return response;
        }

        public static object Ancestors(BridgeRequestContext ctx)
        {
            string identifier = ResolveIdentifier(ctx);
            if (identifier == null)
            {
                return BridgeResponse.Failure("invalid_argument", "path or instanceId is required");
            }

            NodePath.ResolveResult resolved = NodePath.Resolve(identifier, ctx.GetQuery("scene"));
            if (!resolved.Ok)
            {
                return BridgeResponse.Failure(resolved.ErrorCode, resolved.ErrorMessage);
            }

            Type componentType = null;
            string componentRaw = ctx.GetQuery("component");
            if (componentRaw != null)
            {
                TypeResolveResult typeResult = TypeResolver.ResolveComponentType(componentRaw);
                if (!typeResult.Ok)
                {
                    return BridgeResponse.Failure(typeResult.ErrorCode, typeResult.ErrorMessage);
                }

                componentType = typeResult.Type;
            }

            JsonValue ancestors = JsonValue.NewArray();
            Transform current = resolved.Node.parent;
            while (current != null)
            {
                if (componentType == null || current.gameObject.GetComponent(componentType) != null)
                {
                    ancestors.Add(NodeSerializer.BuildSummary(current));
                }

                current = current.parent;
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["ancestors"] = ancestors;
            return response;
        }

        public static object Inspect(BridgeRequestContext ctx)
        {
            string identifier = ResolveIdentifier(ctx);
            if (identifier == null)
            {
                return BridgeResponse.Failure("invalid_argument", "path or instanceId is required");
            }

            NodePath.ResolveResult resolved = NodePath.Resolve(identifier, ctx.GetQuery("scene"));
            if (!resolved.Ok)
            {
                return BridgeResponse.Failure(resolved.ErrorCode, resolved.ErrorMessage);
            }

            JsonValue response = JsonValue.NewObject();
            response["ok"] = true;
            response["node"] = NodeInspector.BuildInspect(resolved.Node);
            return response;
        }

        private static string ResolveIdentifier(BridgeRequestContext ctx)
        {
            string path = ctx.GetQuery("path");
            if (!string.IsNullOrEmpty(path))
            {
                return path;
            }

            return ctx.GetQuery("instanceId");
        }

        /// <returns>false 表示求值预算耗尽（未能扫完 depth 范围内的全部节点）。</returns>
        private static bool CollectBfs(Transform root, int depth, EvalBudget budget, List<Transform> output)
        {
            Queue<(Transform Node, int Depth)> queue = new Queue<(Transform, int)>();
            queue.Enqueue((root, 0));

            while (queue.Count > 0)
            {
                (Transform node, int nodeDepth) = queue.Dequeue();
                if (!budget.TryConsume())
                {
                    return false;
                }

                output.Add(node);

                if (depth >= 0 && nodeDepth >= depth)
                {
                    continue;
                }

                foreach (Transform child in HierarchyScan.GetChildren(node))
                {
                    queue.Enqueue((child, nodeDepth + 1));
                }
            }

            return true;
        }

        /// <returns>false 表示求值预算耗尽（未能扫完全部候选节点）。</returns>
        private static bool CollectMatches(FindCriteria criteria, string sceneFilter, EvalBudget budget, List<Transform> output)
        {
            if (criteria.Under != null)
            {
                // "under" 限定子树，不含锚点自身——只遍历它的子孙。
                foreach (Transform child in HierarchyScan.GetChildren(criteria.Under))
                {
                    if (!WalkSubtree(child, criteria, budget, output))
                    {
                        return false;
                    }
                }

                return true;
            }

            foreach (HierarchyScan.SceneRoots sceneRoots in HierarchyScan.GetAllScenesWithRoots())
            {
                if (!sceneRoots.IsLoaded)
                {
                    continue;
                }

                if (!string.IsNullOrEmpty(sceneFilter) && !string.Equals(sceneRoots.SceneName, sceneFilter, StringComparison.Ordinal))
                {
                    continue;
                }

                foreach (Transform root in sceneRoots.Roots)
                {
                    if (!WalkSubtree(root, criteria, budget, output))
                    {
                        return false;
                    }
                }
            }

            return true;
        }

        private static bool WalkSubtree(Transform node, FindCriteria criteria, EvalBudget budget, List<Transform> output)
        {
            if (!budget.TryConsume())
            {
                return false;
            }

            if (criteria.Matches(node.gameObject, node))
            {
                output.Add(node);
            }

            foreach (Transform child in HierarchyScan.GetChildren(node))
            {
                if (!WalkSubtree(child, criteria, budget, output))
                {
                    return false;
                }
            }

            return true;
        }

        private static void SortMatches(List<Transform> matches, FindCriteria criteria)
        {
            List<(Transform Node, IComparable Key, string Path)> keyed = new List<(Transform, IComparable, string)>();
            foreach (Transform node in matches)
            {
                keyed.Add((node, criteria.GetSortKey(node.gameObject), NodePath.BuildPath(node)));
            }

            int direction = criteria.SortOrder == "desc" ? -1 : 1;
            keyed.Sort((a, b) =>
            {
                if (a.Key == null && b.Key == null)
                {
                    return string.CompareOrdinal(a.Path, b.Path);
                }

                if (a.Key == null)
                {
                    return 1;
                }

                if (b.Key == null)
                {
                    return -1;
                }

                int comparison = direction * CompareComparable(a.Key, b.Key);
                return comparison != 0 ? comparison : string.CompareOrdinal(a.Path, b.Path);
            });

            matches.Clear();
            foreach ((Transform node, IComparable _, string _) in keyed)
            {
                matches.Add(node);
            }
        }

        private static int CompareComparable(IComparable a, IComparable b)
        {
            try
            {
                return a.CompareTo(b);
            }
            catch (ArgumentException)
            {
                return string.CompareOrdinal(a.ToString(), b.ToString());
            }
        }
    }
}
