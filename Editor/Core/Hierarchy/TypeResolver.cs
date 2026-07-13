using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Hierarchy
{
    public sealed class TypeResolveResult
    {
        public bool Ok;
        public Type Type;
        public string ErrorCode;
        public string ErrorMessage;

        public static TypeResolveResult Success(Type type) => new TypeResolveResult { Ok = true, Type = type };

        public static TypeResolveResult Fail(string errorCode, string errorMessage) =>
            new TypeResolveResult { Ok = false, ErrorCode = errorCode, ErrorMessage = errorMessage };
    }

    /// <summary>
    /// 组件/接口的短名 → 类型解析。短名歧义时返回候选 FQN 列表交调用方组装错误信息，
    /// 派生类匹配用 <see cref="Type.IsAssignableFrom"/>（componentType 是查询给的基类/接口，
    /// 实际组件类型是派生类）。
    /// </summary>
    public static class TypeResolver
    {
        private static List<Type> cachedInterfaceTypes;

        public static TypeResolveResult ResolveComponentType(string nameOrFqn)
        {
            return ResolveFromCandidates(nameOrFqn, TypeCache.GetTypesDerivedFrom<Component>(), "unknown_component", "ambiguous_component");
        }

        public static TypeResolveResult ResolveInterfaceType(string nameOrFqn)
        {
            return ResolveFromCandidates(nameOrFqn, AllInterfaceTypes(), "unknown_component", "ambiguous_component");
        }

        public static bool ComponentMatches(Type queryType, Component component)
        {
            return component != null && queryType.IsAssignableFrom(component.GetType());
        }

        private static TypeResolveResult ResolveFromCandidates(
            string nameOrFqn,
            IEnumerable<Type> candidates,
            string notFoundCode,
            string ambiguousCode)
        {
            if (string.IsNullOrWhiteSpace(nameOrFqn))
            {
                return TypeResolveResult.Fail("invalid_argument", "type name is required");
            }

            if (nameOrFqn.Contains('.'))
            {
                foreach (Type candidate in candidates)
                {
                    if (string.Equals(candidate.FullName, nameOrFqn, StringComparison.Ordinal))
                    {
                        return TypeResolveResult.Success(candidate);
                    }
                }

                return TypeResolveResult.Fail(notFoundCode, $"未找到类型：{nameOrFqn}");
            }

            List<Type> shortNameMatches = new List<Type>();
            foreach (Type candidate in candidates)
            {
                if (string.Equals(candidate.Name, nameOrFqn, StringComparison.Ordinal))
                {
                    shortNameMatches.Add(candidate);
                }
            }

            if (shortNameMatches.Count == 0)
            {
                return TypeResolveResult.Fail(notFoundCode, $"未找到类型：{nameOrFqn}");
            }

            if (shortNameMatches.Count > 1)
            {
                List<string> fqns = shortNameMatches.ConvertAll(t => t.FullName);
                return TypeResolveResult.Fail(ambiguousCode, $"类型名 \"{nameOrFqn}\" 有歧义，候选：{string.Join(", ", fqns)}");
            }

            return TypeResolveResult.Success(shortNameMatches[0]);
        }

        /// <summary>
        /// TypeCache 只索引类，不索引"所有接口"；接口短名解析退化为扫描已加载程序集，
        /// 结果按 AppDomain 生命周期缓存（domain reload 会清空静态字段，天然失效重建）。
        /// </summary>
        private static List<Type> AllInterfaceTypes()
        {
            if (cachedInterfaceTypes != null)
            {
                return cachedInterfaceTypes;
            }

            List<Type> result = new List<Type>();
            foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type[] types;
                try
                {
                    types = assembly.GetTypes();
                }
                catch (ReflectionTypeLoadException ex)
                {
                    types = Array.FindAll(ex.Types, t => t != null);
                }
                catch (Exception)
                {
                    continue;
                }

                foreach (Type type in types)
                {
                    if (type.IsInterface)
                    {
                        result.Add(type);
                    }
                }
            }

            cachedInterfaceTypes = result;
            return result;
        }
    }
}
