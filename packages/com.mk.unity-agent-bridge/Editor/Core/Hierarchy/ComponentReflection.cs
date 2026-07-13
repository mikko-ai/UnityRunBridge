using System;
using System.Globalization;
using System.Reflection;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Hierarchy
{
    /// <summary>
    /// `where` / `sortBy` 共用的反射取值与比较逻辑：格式恒为 "Component.property"，
    /// 只读公共实例属性或字段，取值失败（组件不存在/成员不存在/类型不支持比较）时
    /// 由调用方决定语义（where 报错，sortBy 排序键缺失的节点排最后）。
    /// </summary>
    public static class ComponentReflection
    {
        private static readonly string[] Operators = { "!=", ">=", "<=", "=", ">", "<" };

        public static bool TryParseMemberPath(string memberPath, out string componentName, out string memberName)
        {
            componentName = null;
            memberName = null;
            if (string.IsNullOrWhiteSpace(memberPath))
            {
                return false;
            }

            int dot = memberPath.LastIndexOf('.');
            if (dot <= 0 || dot >= memberPath.Length - 1)
            {
                return false;
            }

            componentName = memberPath.Substring(0, dot);
            memberName = memberPath.Substring(dot + 1);
            return true;
        }

        public static bool TryParseWhereExpression(string expression, out string memberPath, out string op, out string literal)
        {
            memberPath = null;
            op = null;
            literal = null;
            if (string.IsNullOrWhiteSpace(expression))
            {
                return false;
            }

            foreach (string candidate in Operators)
            {
                int index = expression.IndexOf(candidate, StringComparison.Ordinal);
                if (index <= 0)
                {
                    continue;
                }

                memberPath = expression.Substring(0, index);
                op = candidate;
                literal = expression.Substring(index + candidate.Length);
                return true;
            }

            return false;
        }

        /// <summary>取节点上目标组件（含派生类）的成员值；组件不存在或成员不存在返回 false。</summary>
        public static bool TryGetMemberValue(GameObject go, Type componentType, string memberName, out object value, out string error)
        {
            value = null;
            error = null;
            Component component = go.GetComponent(componentType);
            if (component == null)
            {
                return false;
            }

            Type actualType = component.GetType();
            PropertyInfo property = actualType.GetProperty(memberName, BindingFlags.Public | BindingFlags.Instance);
            if (property != null && property.CanRead && property.GetIndexParameters().Length == 0)
            {
                try
                {
                    value = property.GetValue(component);
                    return true;
                }
                catch (Exception ex)
                {
                    error = ex.Message;
                    return false;
                }
            }

            FieldInfo field = actualType.GetField(memberName, BindingFlags.Public | BindingFlags.Instance);
            if (field != null)
            {
                try
                {
                    value = field.GetValue(component);
                    return true;
                }
                catch (Exception ex)
                {
                    error = ex.Message;
                    return false;
                }
            }

            error = $"成员不存在：{actualType.FullName}.{memberName}";
            return false;
        }

        public static bool TryCompare(object actual, string op, string literal, out bool matches, out string error)
        {
            matches = false;
            error = null;

            if (actual is bool boolValue)
            {
                if (!bool.TryParse(literal, out bool literalBool))
                {
                    error = $"无法把 \"{literal}\" 解析为 bool";
                    return false;
                }

                return TryEqualityOnly(boolValue == literalBool, boolValue.Equals(literalBool), op, out matches, out error);
            }

            if (actual is Enum enumValue)
            {
                bool equal = string.Equals(enumValue.ToString(), literal, StringComparison.OrdinalIgnoreCase);
                return TryEqualityOnly(equal, equal, op, out matches, out error);
            }

            if (actual is string stringValue)
            {
                bool equal = string.Equals(stringValue, literal, StringComparison.Ordinal);
                return TryEqualityOnly(equal, equal, op, out matches, out error);
            }

            if (IsNumeric(actual))
            {
                double actualNumber = Convert.ToDouble(actual, CultureInfo.InvariantCulture);
                if (!double.TryParse(literal, NumberStyles.Float, CultureInfo.InvariantCulture, out double literalNumber))
                {
                    error = $"无法把 \"{literal}\" 解析为数字";
                    return false;
                }

                matches = op switch
                {
                    "=" => actualNumber == literalNumber,
                    "!=" => actualNumber != literalNumber,
                    ">" => actualNumber > literalNumber,
                    "<" => actualNumber < literalNumber,
                    ">=" => actualNumber >= literalNumber,
                    "<=" => actualNumber <= literalNumber,
                    _ => false
                };
                return true;
            }

            error = $"不支持比较的类型：{actual?.GetType().FullName ?? "null"}";
            return false;
        }

        /// <summary>返回可用于排序的键；取不到时返回 null（sortBy 语义：排最后）。</summary>
        public static IComparable GetSortKey(object value)
        {
            switch (value)
            {
                case null:
                    return null;
                case IComparable comparable when IsNumeric(value):
                    return Convert.ToDouble(value, CultureInfo.InvariantCulture);
                case Enum enumValue:
                    return enumValue.ToString();
                case IComparable comparableValue:
                    return comparableValue;
                default:
                    return null;
            }
        }

        private static bool TryEqualityOnly(bool equalResult, bool _, string op, out bool matches, out string error)
        {
            matches = false;
            error = null;
            switch (op)
            {
                case "=":
                    matches = equalResult;
                    return true;
                case "!=":
                    matches = !equalResult;
                    return true;
                default:
                    error = $"该类型只支持 = / != 比较，收到：{op}";
                    return false;
            }
        }

        private static bool IsNumeric(object value)
        {
            return value is sbyte or byte or short or ushort or int or uint or long or ulong or float or double or decimal;
        }
    }
}
