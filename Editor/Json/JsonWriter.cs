using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace Mk.UnityAgentBridge.Editor.Json
{
    /// <summary>
    /// 自写 JSON 序列化器。支持 <see cref="JsonValue"/>、<see cref="IDictionary"/>（key 用 ToString()）、
    /// <see cref="IEnumerable"/>（除 string 外）、字符串/布尔/整型/浮点/枚举/null。
    /// 不支持的类型直接抛异常（不静默降级为字符串），避免掩盖调用方的结构性错误。
    /// </summary>
    public static class JsonWriter
    {
        public static string Serialize(object value)
        {
            StringBuilder builder = new StringBuilder();
            WriteValue(builder, value);
            return builder.ToString();
        }

        private static void WriteValue(StringBuilder builder, object value)
        {
            switch (value)
            {
                case null:
                    builder.Append("null");
                    return;
                case JsonValue jsonValue:
                    WriteJsonValue(builder, jsonValue);
                    return;
                case bool boolValue:
                    builder.Append(boolValue ? "true" : "false");
                    return;
                case string stringValue:
                    WriteString(builder, stringValue);
                    return;
                case char charValue:
                    WriteString(builder, charValue.ToString());
                    return;
                case sbyte:
                case byte:
                case short:
                case ushort:
                case int:
                case uint:
                case long:
                case ulong:
                    builder.Append(Convert.ToInt64(value, CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture));
                    return;
                case float floatValue:
                    WriteFloat(builder, floatValue);
                    return;
                case double doubleValue:
                    WriteFloat(builder, doubleValue);
                    return;
                case Enum enumValue:
                    WriteString(builder, enumValue.ToString());
                    return;
                case IDictionary dictionary:
                    WriteDictionary(builder, dictionary);
                    return;
                case IEnumerable enumerable:
                    WriteArray(builder, enumerable);
                    return;
                default:
                    throw new JsonWriterException(
                        $"JsonWriter 不支持序列化类型 {value.GetType().FullName}；" +
                        "请转换为 JsonValue、IDictionary<string,object> 或 IEnumerable 后再传入。"
                    );
            }
        }

        private static void WriteFloat(StringBuilder builder, double value)
        {
            if (double.IsNaN(value) || double.IsInfinity(value))
            {
                throw new JsonWriterException("NaN/Infinity 不是合法 JSON 数值");
            }

            string text = value.ToString("R", CultureInfo.InvariantCulture);
            // "R" 对整数值的 double（如 4.0）只输出 "4"，JSON 数字语法允许，
            // 但为了让消费方能稳定区分“这是一个浮点字段”，補上 ".0"。
            if (text.IndexOfAny(DecimalMarkers) < 0)
            {
                text += ".0";
            }

            builder.Append(text);
        }

        private static readonly char[] DecimalMarkers = { '.', 'e', 'E' };

        private static void WriteJsonValue(StringBuilder builder, JsonValue value)
        {
            switch (value.Type)
            {
                case JsonValueType.Null:
                    builder.Append("null");
                    return;
                case JsonValueType.Boolean:
                    builder.Append(value.AsBoolean ? "true" : "false");
                    return;
                case JsonValueType.Number:
                    if (value.IsIntegerNumber)
                    {
                        builder.Append(value.AsLong.ToString(CultureInfo.InvariantCulture));
                    }
                    else
                    {
                        WriteFloat(builder, value.AsDouble);
                    }

                    return;
                case JsonValueType.String:
                    WriteString(builder, value.AsString);
                    return;
                case JsonValueType.Array:
                    builder.Append('[');
                    bool firstItem = true;
                    foreach (JsonValue item in value.Items)
                    {
                        if (!firstItem)
                        {
                            builder.Append(',');
                        }

                        firstItem = false;
                        WriteJsonValue(builder, item);
                    }

                    builder.Append(']');
                    return;
                case JsonValueType.Object:
                    builder.Append('{');
                    bool firstProp = true;
                    foreach (KeyValuePair<string, JsonValue> property in value.Properties)
                    {
                        if (!firstProp)
                        {
                            builder.Append(',');
                        }

                        firstProp = false;
                        WriteString(builder, property.Key);
                        builder.Append(':');
                        WriteJsonValue(builder, property.Value);
                    }

                    builder.Append('}');
                    return;
                default:
                    throw new JsonWriterException($"未知的 JsonValueType: {value.Type}");
            }
        }

        private static void WriteDictionary(StringBuilder builder, IDictionary dictionary)
        {
            builder.Append('{');
            bool first = true;
            foreach (DictionaryEntry entry in dictionary)
            {
                if (!first)
                {
                    builder.Append(',');
                }

                first = false;
                WriteString(builder, Convert.ToString(entry.Key, CultureInfo.InvariantCulture));
                builder.Append(':');
                WriteValue(builder, entry.Value);
            }

            builder.Append('}');
        }

        private static void WriteArray(StringBuilder builder, IEnumerable enumerable)
        {
            builder.Append('[');
            bool first = true;
            foreach (object item in enumerable)
            {
                if (!first)
                {
                    builder.Append(',');
                }

                first = false;
                WriteValue(builder, item);
            }

            builder.Append(']');
        }

        private static void WriteString(StringBuilder builder, string value)
        {
            builder.Append('"');
            foreach (char c in value)
            {
                switch (c)
                {
                    case '"':
                        builder.Append("\\\"");
                        break;
                    case '\\':
                        builder.Append("\\\\");
                        break;
                    case '\b':
                        builder.Append("\\b");
                        break;
                    case '\f':
                        builder.Append("\\f");
                        break;
                    case '\n':
                        builder.Append("\\n");
                        break;
                    case '\r':
                        builder.Append("\\r");
                        break;
                    case '\t':
                        builder.Append("\\t");
                        break;
                    default:
                        if (c < 0x20)
                        {
                            builder.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        }
                        else
                        {
                            builder.Append(c);
                        }

                        break;
                }
            }

            builder.Append('"');
        }
    }
}
