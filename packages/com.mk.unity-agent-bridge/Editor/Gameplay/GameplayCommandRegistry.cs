using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;

namespace Mk.UnityAgentBridge.Editor.Gameplay
{
    /// <summary>
    /// 零侵入 gameplay 命令发现：反射扫描项目程序集里被短名为 "AgentCommandAttribute" 的
    /// 任意 attribute（不限命名空间）标注的公开静态方法，游戏可自定义同名 attribute 而不依赖
    /// 本包。同时支持按完全限定名（Namespace.Class.Method）直接解析白名单命令。
    ///
    /// 扫描只在首次访问时执行一次，结果缓存到静态字段；domain reload 会清空静态字段，
    /// 天然触发下一次访问重新扫描，不需要显式监听 reload 事件。
    /// </summary>
    internal static class GameplayCommandRegistry
    {
        private const string AttributeShortName = "AgentCommandAttribute";

        private static readonly string[] ExcludedAssemblyPrefixes =
        {
            "Unity", "System", "mscorlib", "netstandard", "Mono.", "nunit"
        };

        private static readonly Dictionary<Type, string> SupportedTypeNames = new Dictionary<Type, string>
        {
            [typeof(bool)] = "bool",
            [typeof(int)] = "int",
            [typeof(long)] = "long",
            [typeof(float)] = "float",
            [typeof(double)] = "double",
            [typeof(string)] = "string"
        };

        private static readonly string OwnAssemblyName = typeof(GameplayCommandRegistry).Assembly.GetName().Name;

        private static Dictionary<string, CommandInfo> attributeCommandsCache;

        public sealed class ParamInfo
        {
            public string Name;
            public string Type;
        }

        public sealed class CommandInfo
        {
            public string Name;
            public string AssemblyName;
            public MethodInfo Method;
            public List<ParamInfo> Parameters;
            public string ReturnType;
            public string Source;
            public bool Invocable;
            public string InvocableReason;
        }

        public static IReadOnlyList<CommandInfo> DiscoverAttributeCommands()
        {
            if (attributeCommandsCache == null)
            {
                attributeCommandsCache = ScanAttributeCommands();
            }

            return attributeCommandsCache.Values.ToList();
        }

        /// <summary>仅供 EditMode 测试在同一 domain 内强制重新扫描（例如测试新增了带 attribute 的类型）。</summary>
        internal static void ResetCacheForTests()
        {
            attributeCommandsCache = null;
        }

        /// <summary>
        /// 统一命令解析入口：先按名称匹配 attribute 发现的命令，找不到再尝试按完全限定名
        /// 解析白名单直调命令。GameplayController 与测试都应通过此方法解析命令，
        /// 不直接拼装两条通道的判断逻辑。
        /// </summary>
        public static bool Resolve(
            string commandName,
            IReadOnlyList<string> whitelist,
            out CommandInfo command,
            out string errorCode,
            out string errorMessage)
        {
            foreach (CommandInfo attributeCommand in DiscoverAttributeCommands())
            {
                if (string.Equals(attributeCommand.Name, commandName, StringComparison.Ordinal))
                {
                    command = attributeCommand;
                    errorCode = null;
                    errorMessage = null;
                    return true;
                }
            }

            return TryResolveWhitelistCommand(commandName, whitelist, out command, out errorCode, out errorMessage);
        }

        public static bool TryResolveWhitelistCommand(
            string fullyQualifiedName,
            IReadOnlyList<string> whitelist,
            out CommandInfo command,
            out string errorCode,
            out string errorMessage)
        {
            command = null;
            errorCode = null;
            errorMessage = null;

            if (whitelist == null || !whitelist.Contains(fullyQualifiedName, StringComparer.Ordinal))
            {
                errorCode = "command_not_found";
                errorMessage = $"命令不在白名单中：{fullyQualifiedName}";
                return false;
            }

            int lastDot = fullyQualifiedName.LastIndexOf('.');
            if (lastDot <= 0 || lastDot == fullyQualifiedName.Length - 1)
            {
                errorCode = "command_not_found";
                errorMessage = $"非法的命令全名（应为 Namespace.Class.Method）：{fullyQualifiedName}";
                return false;
            }

            string typeName = fullyQualifiedName.Substring(0, lastDot);
            string methodName = fullyQualifiedName.Substring(lastDot + 1);

            Type type = FindTypeByFullName(typeName);
            if (type == null)
            {
                errorCode = "command_not_found";
                errorMessage = $"找不到类型：{typeName}";
                return false;
            }

            MethodInfo method;
            try
            {
                method = type.GetMethod(methodName, BindingFlags.Public | BindingFlags.Static);
            }
            catch (AmbiguousMatchException)
            {
                errorCode = "unsupported_signature";
                errorMessage = $"方法存在多个重载，无法唯一确定：{fullyQualifiedName}";
                return false;
            }

            if (method == null)
            {
                errorCode = "command_not_found";
                errorMessage = $"找不到公开静态方法：{fullyQualifiedName}";
                return false;
            }

            command = BuildCommandInfo(type, method, null, type.Assembly.GetName().Name, "whitelist");
            return true;
        }

        public static bool TryGetSupportedTypeName(Type type, out string typeName)
        {
            if (SupportedTypeNames.TryGetValue(type, out typeName))
            {
                return true;
            }

            if (type.IsEnum)
            {
                typeName = "enum:" + type.FullName;
                return true;
            }

            typeName = type.FullName;
            return false;
        }

        private static Dictionary<string, CommandInfo> ScanAttributeCommands()
        {
            Dictionary<string, CommandInfo> result = new Dictionary<string, CommandInfo>(StringComparer.Ordinal);

            foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                string assemblyName = assembly.GetName().Name;
                if (IsExcludedAssembly(assemblyName))
                {
                    continue;
                }

                Type[] types = GetLoadableTypes(assembly);
                foreach (Type type in types)
                {
                    if (type == null)
                    {
                        continue;
                    }

                    foreach (MethodInfo method in type.GetMethods(
                        BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly))
                    {
                        object matchedAttribute = FindAgentCommandAttribute(method);
                        if (matchedAttribute == null)
                        {
                            continue;
                        }

                        CommandInfo info = BuildCommandInfo(type, method, matchedAttribute, assemblyName, "attribute");
                        result[info.Name] = info;
                    }
                }
            }

            return result;
        }

        private static object FindAgentCommandAttribute(MethodInfo method)
        {
            object[] attributes;
            try
            {
                attributes = method.GetCustomAttributes(true);
            }
            catch (Exception)
            {
                return null;
            }

            return attributes.FirstOrDefault(a => a.GetType().Name == AttributeShortName);
        }

        private static CommandInfo BuildCommandInfo(Type type, MethodInfo method, object attribute, string assemblyName, string source)
        {
            string name = ResolveCustomName(attribute) ?? $"{type.Name}.{method.Name}";

            List<ParamInfo> parameters = new List<ParamInfo>();
            bool invocable = true;
            string reason = null;

            foreach (ParameterInfo parameter in method.GetParameters())
            {
                bool supported = TryGetSupportedTypeName(parameter.ParameterType, out string typeName);
                parameters.Add(new ParamInfo { Name = parameter.Name, Type = typeName });
                if (!supported)
                {
                    invocable = false;
                    reason = $"不支持的参数类型：{parameter.Name} ({parameter.ParameterType.FullName})";
                }
            }

            string returnType;
            if (method.ReturnType == typeof(void))
            {
                returnType = "void";
            }
            else if (TryGetSupportedTypeName(method.ReturnType, out string returnTypeName))
            {
                returnType = returnTypeName;
            }
            else
            {
                returnType = method.ReturnType.FullName;
                invocable = false;
                reason ??= $"不支持的返回值类型：{method.ReturnType.FullName}";
            }

            return new CommandInfo
            {
                Name = name,
                AssemblyName = assemblyName,
                Method = method,
                Parameters = parameters,
                ReturnType = returnType,
                Source = source,
                Invocable = invocable,
                InvocableReason = reason
            };
        }

        private static string ResolveCustomName(object attribute)
        {
            if (attribute == null)
            {
                return null;
            }

            PropertyInfo nameProperty = attribute.GetType().GetProperty("Name", BindingFlags.Public | BindingFlags.Instance);
            if (nameProperty == null || nameProperty.PropertyType != typeof(string))
            {
                return null;
            }

            string value = nameProperty.GetValue(attribute) as string;
            return string.IsNullOrEmpty(value) ? null : value;
        }

        private static Type FindTypeByFullName(string fullName)
        {
            foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type type;
                try
                {
                    type = assembly.GetType(fullName, throwOnError: false);
                }
                catch (Exception)
                {
                    type = null;
                }

                if (type != null)
                {
                    return type;
                }
            }

            return null;
        }

        private static Type[] GetLoadableTypes(Assembly assembly)
        {
            try
            {
                return assembly.GetTypes();
            }
            catch (ReflectionTypeLoadException ex)
            {
                return ex.Types.Where(t => t != null).ToArray();
            }
            catch (Exception)
            {
                return Array.Empty<Type>();
            }
        }

        private static bool IsExcludedAssembly(string assemblyName)
        {
            if (string.IsNullOrEmpty(assemblyName) || assemblyName == OwnAssemblyName)
            {
                return true;
            }

            foreach (string prefix in ExcludedAssemblyPrefixes)
            {
                if (assemblyName.StartsWith(prefix, StringComparison.Ordinal))
                {
                    return true;
                }
            }

            return false;
        }
    }
}
