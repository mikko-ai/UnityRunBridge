using System;
using System.Text.RegularExpressions;
using Mk.UnityAgentBridge.Editor.Routing;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Hierarchy
{
    internal sealed class FindQueryResult
    {
        public bool Ok;
        public FindCriteria Criteria;
        public string ErrorCode;
        public string ErrorMessage;

        public static FindQueryResult Success(FindCriteria criteria) => new FindQueryResult { Ok = true, Criteria = criteria };

        public static FindQueryResult Fail(string errorCode, string errorMessage) =>
            new FindQueryResult { Ok = false, ErrorCode = errorCode, ErrorMessage = errorMessage };
    }

    /// <summary>find 过滤器全 AND 求值；解析失败（歧义组件、非法正则等）在 <see cref="FindQuery.Parse"/> 阶段一次性报出。</summary>
    internal sealed class FindCriteria
    {
        public string Name;
        public string NameContains;
        public Regex NameRegex;
        public string PathGlob;
        public Type ComponentType;
        public Type InterfaceType;
        public bool MissingScriptOnly;
        public string Tag;
        public int? Layer;
        public Transform Under;
        public string ActiveFilter = "all";
        public string TextContains;

        public Type WhereComponentType;
        public string WhereMemberName;
        public string WhereOp;
        public string WhereLiteral;

        public Type SortComponentType;
        public string SortMemberName;
        public string SortOrder = "asc";

        public bool CountOnly;

        public bool Matches(GameObject go, Transform transform)
        {
            if (Name != null && go.name != Name)
            {
                return false;
            }

            if (NameContains != null && go.name.IndexOf(NameContains, StringComparison.OrdinalIgnoreCase) < 0)
            {
                return false;
            }

            if (NameRegex != null && !NameRegex.IsMatch(go.name))
            {
                return false;
            }

            if (PathGlob != null && !GlobMatch(PathGlob, NodePath.BuildPath(transform)))
            {
                return false;
            }

            if (ComponentType != null && go.GetComponent(ComponentType) == null)
            {
                return false;
            }

            if (InterfaceType != null && !HasComponentImplementing(go, InterfaceType))
            {
                return false;
            }

            if (MissingScriptOnly && !NodeSerializer.HasMissingScript(go))
            {
                return false;
            }

            if (Tag != null && !SafeTagEquals(go, Tag))
            {
                return false;
            }

            if (Layer.HasValue && go.layer != Layer.Value)
            {
                return false;
            }

            if (Under != null && (transform == Under || !transform.IsChildOf(Under)))
            {
                return false;
            }

            if (ActiveFilter == "only" && !go.activeInHierarchy)
            {
                return false;
            }

            if (ActiveFilter == "none" && go.activeInHierarchy)
            {
                return false;
            }

            if (TextContains != null)
            {
                string text = NodeSerializer.TryGetText(go);
                if (text == null || text.IndexOf(TextContains, StringComparison.OrdinalIgnoreCase) < 0)
                {
                    return false;
                }
            }

            if (WhereComponentType != null)
            {
                if (!ComponentReflection.TryGetMemberValue(go, WhereComponentType, WhereMemberName, out object value, out string _))
                {
                    return false;
                }

                if (!ComponentReflection.TryCompare(value, WhereOp, WhereLiteral, out bool matches, out string _) || !matches)
                {
                    return false;
                }
            }

            return true;
        }

        public IComparable GetSortKey(GameObject go)
        {
            if (SortComponentType == null)
            {
                return null;
            }

            return ComponentReflection.TryGetMemberValue(go, SortComponentType, SortMemberName, out object value, out string _)
                ? ComponentReflection.GetSortKey(value)
                : null;
        }

        private static bool HasComponentImplementing(GameObject go, Type interfaceType)
        {
            foreach (Component component in go.GetComponents<Component>())
            {
                if (component != null && interfaceType.IsInstanceOfType(component))
                {
                    return true;
                }
            }

            return false;
        }

        private static bool SafeTagEquals(GameObject go, string tag)
        {
            try
            {
                return go.CompareTag(tag);
            }
            catch (UnityException)
            {
                return false;
            }
        }

        private static bool GlobMatch(string glob, string path)
        {
            string pattern = "^" + Regex.Escape(glob)
                .Replace(@"\*\*", ".*")
                .Replace(@"\*", "[^/]*") + "$";
            return Regex.IsMatch(path, pattern);
        }
    }

    internal static class FindQuery
    {
        public static FindQueryResult Parse(BridgeRequestContext ctx)
        {
            FindCriteria criteria = new FindCriteria
            {
                Name = ctx.GetQuery("name"),
                NameContains = ctx.GetQuery("nameContains"),
                PathGlob = ctx.GetQuery("pathGlob"),
                Tag = ctx.GetQuery("tag"),
                TextContains = ctx.GetQuery("textContains"),
                MissingScriptOnly = ctx.GetQueryBool("missingScript", false),
                CountOnly = ctx.GetQueryBool("countOnly", false)
            };

            string nameRegexRaw = ctx.GetQuery("nameRegex");
            if (nameRegexRaw != null)
            {
                try
                {
                    criteria.NameRegex = new Regex(nameRegexRaw);
                }
                catch (ArgumentException ex)
                {
                    return FindQueryResult.Fail("invalid_argument", $"nameRegex 编译失败：{ex.Message}");
                }
            }

            string componentRaw = ctx.GetQuery("component");
            if (componentRaw != null)
            {
                TypeResolveResult resolved = TypeResolver.ResolveComponentType(componentRaw);
                if (!resolved.Ok)
                {
                    return FindQueryResult.Fail(resolved.ErrorCode, resolved.ErrorMessage);
                }

                criteria.ComponentType = resolved.Type;
            }

            string interfaceRaw = ctx.GetQuery("interface");
            if (interfaceRaw != null)
            {
                TypeResolveResult resolved = TypeResolver.ResolveInterfaceType(interfaceRaw);
                if (!resolved.Ok)
                {
                    return FindQueryResult.Fail(resolved.ErrorCode, resolved.ErrorMessage);
                }

                criteria.InterfaceType = resolved.Type;
            }

            string layerRaw = ctx.GetQuery("layer");
            if (layerRaw != null)
            {
                if (int.TryParse(layerRaw, out int layerNumber))
                {
                    criteria.Layer = layerNumber;
                }
                else
                {
                    int layerByName = LayerMask.NameToLayer(layerRaw);
                    if (layerByName < 0)
                    {
                        return FindQueryResult.Fail("invalid_argument", $"未知 layer：{layerRaw}");
                    }

                    criteria.Layer = layerByName;
                }
            }

            string underRaw = ctx.GetQuery("under");
            if (underRaw != null)
            {
                NodePath.ResolveResult resolved = NodePath.Resolve(underRaw, ctx.GetQuery("scene"));
                if (!resolved.Ok)
                {
                    return FindQueryResult.Fail(resolved.ErrorCode, resolved.ErrorMessage);
                }

                criteria.Under = resolved.Node;
            }

            string activeRaw = ctx.GetQuery("active", "all");
            if (activeRaw != "only" && activeRaw != "none" && activeRaw != "all")
            {
                return FindQueryResult.Fail("invalid_argument", $"active 必须是 only/none/all，收到：{activeRaw}");
            }

            criteria.ActiveFilter = activeRaw;

            string whereRaw = ctx.GetQuery("where");
            if (whereRaw != null)
            {
                if (!ComponentReflection.TryParseWhereExpression(whereRaw, out string memberPath, out string op, out string literal) ||
                    !ComponentReflection.TryParseMemberPath(memberPath, out string componentName, out string memberName))
                {
                    return FindQueryResult.Fail("invalid_argument", $"where 表达式格式错误：{whereRaw}");
                }

                TypeResolveResult resolved = TypeResolver.ResolveComponentType(componentName);
                if (!resolved.Ok)
                {
                    return FindQueryResult.Fail(resolved.ErrorCode, resolved.ErrorMessage);
                }

                criteria.WhereComponentType = resolved.Type;
                criteria.WhereMemberName = memberName;
                criteria.WhereOp = op;
                criteria.WhereLiteral = literal;
            }

            string sortByRaw = ctx.GetQuery("sortBy");
            if (sortByRaw != null)
            {
                if (!ComponentReflection.TryParseMemberPath(sortByRaw, out string componentName, out string memberName))
                {
                    return FindQueryResult.Fail("invalid_argument", $"sortBy 格式错误：{sortByRaw}");
                }

                TypeResolveResult resolved = TypeResolver.ResolveComponentType(componentName);
                if (!resolved.Ok)
                {
                    return FindQueryResult.Fail(resolved.ErrorCode, resolved.ErrorMessage);
                }

                criteria.SortComponentType = resolved.Type;
                criteria.SortMemberName = memberName;
            }

            string order = ctx.GetQuery("order", "asc");
            if (order != "asc" && order != "desc")
            {
                return FindQueryResult.Fail("invalid_argument", $"order 必须是 asc/desc，收到：{order}");
            }

            criteria.SortOrder = order;

            return FindQueryResult.Success(criteria);
        }
    }
}
