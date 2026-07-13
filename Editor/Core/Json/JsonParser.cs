using System;
using System.Globalization;
using System.Text;

namespace Mk.UnityAgentBridge.Editor.Json
{
    /// <summary>
    /// 自写 JSON 解析器：递归下降，UTF-8/Unicode 转义与代理对由 .NET string 原生支持
    /// （逐个 \uXXXX 追加到 StringBuilder 即可正确重建代理对，无需额外处理）。
    /// 数字按整型优先解析（long），溢出或含小数点/指数时转 double。
    /// 深度上限 64（防止恶意/异常输入导致递归栈溢出），输入大小上限 10MB。
    /// </summary>
    public static class JsonParser
    {
        public const int MaxDepth = 64;
        public const int MaxInputSizeBytes = 10 * 1024 * 1024;

        public static JsonValue Parse(string json)
        {
            if (json == null)
            {
                throw new JsonParseException("输入为 null", 0);
            }

            int byteCount = Encoding.UTF8.GetByteCount(json);
            if (byteCount > MaxInputSizeBytes)
            {
                throw new JsonParseException(
                    $"输入大小 {byteCount} 字节超过上限 {MaxInputSizeBytes} 字节", 0);
            }

            Cursor cursor = new Cursor(json);
            cursor.SkipWhitespace();
            JsonValue result = ParseValue(ref cursor, 0);
            cursor.SkipWhitespace();
            if (!cursor.AtEnd)
            {
                throw new JsonParseException("JSON 结尾之后存在多余内容", cursor.Position);
            }

            return result;
        }

        public static bool TryParse(string json, out JsonValue value, out string error)
        {
            try
            {
                value = Parse(json);
                error = null;
                return true;
            }
            catch (JsonParseException ex)
            {
                value = null;
                error = ex.Message;
                return false;
            }
        }

        private static JsonValue ParseValue(ref Cursor cursor, int depth)
        {
            if (depth > MaxDepth)
            {
                throw new JsonParseException($"嵌套深度超过上限 {MaxDepth}", cursor.Position);
            }

            if (cursor.AtEnd)
            {
                throw new JsonParseException("意外的输入结尾", cursor.Position);
            }

            char c = cursor.Peek();
            switch (c)
            {
                case '{':
                    return ParseObject(ref cursor, depth);
                case '[':
                    return ParseArray(ref cursor, depth);
                case '"':
                    return JsonValue.FromString(ParseStringLiteral(ref cursor));
                case 't':
                    cursor.ExpectLiteral("true");
                    return JsonValue.True;
                case 'f':
                    cursor.ExpectLiteral("false");
                    return JsonValue.False;
                case 'n':
                    cursor.ExpectLiteral("null");
                    return JsonValue.Null;
                default:
                    if (c == '-' || (c >= '0' && c <= '9'))
                    {
                        return ParseNumber(ref cursor);
                    }

                    throw new JsonParseException($"无法识别的字符 '{c}'", cursor.Position);
            }
        }

        private static JsonValue ParseObject(ref Cursor cursor, int depth)
        {
            cursor.Expect('{');
            JsonValue result = JsonValue.NewObject();
            cursor.SkipWhitespace();
            if (cursor.TryConsume('}'))
            {
                return result;
            }

            while (true)
            {
                cursor.SkipWhitespace();
                if (cursor.AtEnd || cursor.Peek() != '"')
                {
                    throw new JsonParseException("对象的键必须是字符串", cursor.Position);
                }

                string key = ParseStringLiteral(ref cursor);
                cursor.SkipWhitespace();
                cursor.Expect(':');
                cursor.SkipWhitespace();
                JsonValue value = ParseValue(ref cursor, depth + 1);
                result[key] = value;
                cursor.SkipWhitespace();

                if (cursor.TryConsume(','))
                {
                    continue;
                }

                cursor.Expect('}');
                return result;
            }
        }

        private static JsonValue ParseArray(ref Cursor cursor, int depth)
        {
            cursor.Expect('[');
            JsonValue result = JsonValue.NewArray();
            cursor.SkipWhitespace();
            if (cursor.TryConsume(']'))
            {
                return result;
            }

            while (true)
            {
                cursor.SkipWhitespace();
                JsonValue value = ParseValue(ref cursor, depth + 1);
                result.Add(value);
                cursor.SkipWhitespace();

                if (cursor.TryConsume(','))
                {
                    continue;
                }

                cursor.Expect(']');
                return result;
            }
        }

        private static string ParseStringLiteral(ref Cursor cursor)
        {
            cursor.Expect('"');
            StringBuilder builder = new StringBuilder();
            while (true)
            {
                if (cursor.AtEnd)
                {
                    throw new JsonParseException("字符串未闭合", cursor.Position);
                }

                char c = cursor.Next();
                if (c == '"')
                {
                    return builder.ToString();
                }

                if (c == '\\')
                {
                    if (cursor.AtEnd)
                    {
                        throw new JsonParseException("字符串转义序列不完整", cursor.Position);
                    }

                    char escape = cursor.Next();
                    switch (escape)
                    {
                        case '"':
                            builder.Append('"');
                            break;
                        case '\\':
                            builder.Append('\\');
                            break;
                        case '/':
                            builder.Append('/');
                            break;
                        case 'b':
                            builder.Append('\b');
                            break;
                        case 'f':
                            builder.Append('\f');
                            break;
                        case 'n':
                            builder.Append('\n');
                            break;
                        case 'r':
                            builder.Append('\r');
                            break;
                        case 't':
                            builder.Append('\t');
                            break;
                        case 'u':
                            builder.Append(ParseUnicodeEscape(ref cursor));
                            break;
                        default:
                            throw new JsonParseException($"非法转义字符 '\\{escape}'", cursor.Position);
                    }

                    continue;
                }

                if (c < 0x20)
                {
                    throw new JsonParseException("字符串中包含未转义的控制字符", cursor.Position);
                }

                builder.Append(c);
            }
        }

        private static char ParseUnicodeEscape(ref Cursor cursor)
        {
            if (cursor.Remaining < 4)
            {
                throw new JsonParseException("\\u 转义序列不完整", cursor.Position);
            }

            string hex = cursor.Take(4);
            if (!ushort.TryParse(hex, NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out ushort code))
            {
                throw new JsonParseException($"非法的 \\u 转义序列 '{hex}'", cursor.Position);
            }

            return (char)code;
        }

        private static JsonValue ParseNumber(ref Cursor cursor)
        {
            int start = cursor.Position;
            bool isFloat = false;

            cursor.TryConsume('-');

            if (cursor.AtEnd || !IsDigit(cursor.Peek()))
            {
                throw new JsonParseException("数字缺少整数部分", cursor.Position);
            }

            if (cursor.Peek() == '0')
            {
                cursor.Next();
            }
            else
            {
                while (!cursor.AtEnd && IsDigit(cursor.Peek()))
                {
                    cursor.Next();
                }
            }

            if (!cursor.AtEnd && cursor.Peek() == '.')
            {
                isFloat = true;
                cursor.Next();
                if (cursor.AtEnd || !IsDigit(cursor.Peek()))
                {
                    throw new JsonParseException("小数点后缺少数字", cursor.Position);
                }

                while (!cursor.AtEnd && IsDigit(cursor.Peek()))
                {
                    cursor.Next();
                }
            }

            if (!cursor.AtEnd && (cursor.Peek() == 'e' || cursor.Peek() == 'E'))
            {
                isFloat = true;
                cursor.Next();
                if (!cursor.AtEnd && (cursor.Peek() == '+' || cursor.Peek() == '-'))
                {
                    cursor.Next();
                }

                if (cursor.AtEnd || !IsDigit(cursor.Peek()))
                {
                    throw new JsonParseException("指数部分缺少数字", cursor.Position);
                }

                while (!cursor.AtEnd && IsDigit(cursor.Peek()))
                {
                    cursor.Next();
                }
            }

            string text = cursor.Slice(start, cursor.Position);

            if (!isFloat && long.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out long longValue))
            {
                return JsonValue.FromInteger(longValue);
            }

            if (!double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out double doubleValue))
            {
                throw new JsonParseException($"非法数字 '{text}'", start);
            }

            return JsonValue.FromDouble(doubleValue);
        }

        private static bool IsDigit(char c) => c >= '0' && c <= '9';

        private struct Cursor
        {
            private readonly string text;
            public int Position;

            public Cursor(string text)
            {
                this.text = text;
                Position = 0;
            }

            public bool AtEnd => Position >= text.Length;
            public int Remaining => text.Length - Position;

            public char Peek() => text[Position];

            public char Next() => text[Position++];

            public string Take(int count)
            {
                string result = text.Substring(Position, count);
                Position += count;
                return result;
            }

            public string Slice(int start, int end) => text.Substring(start, end - start);

            public void SkipWhitespace()
            {
                while (!AtEnd)
                {
                    char c = Peek();
                    if (c == ' ' || c == '\t' || c == '\n' || c == '\r')
                    {
                        Position++;
                    }
                    else
                    {
                        break;
                    }
                }
            }

            public void Expect(char expected)
            {
                if (AtEnd || Peek() != expected)
                {
                    throw new JsonParseException($"期望字符 '{expected}'", Position);
                }

                Position++;
            }

            public bool TryConsume(char expected)
            {
                if (!AtEnd && Peek() == expected)
                {
                    Position++;
                    return true;
                }

                return false;
            }

            public void ExpectLiteral(string literal)
            {
                if (Remaining < literal.Length || text.Substring(Position, literal.Length) != literal)
                {
                    throw new JsonParseException($"期望字面量 '{literal}'", Position);
                }

                Position += literal.Length;
            }
        }
    }
}
