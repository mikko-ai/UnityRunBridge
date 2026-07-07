using System.Text;
using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Json
{
    public sealed class JsonParserTests
    {
        [Test]
        public void Parse_Literals()
        {
            Assert.IsTrue(JsonParser.Parse("true").AsBoolean);
            Assert.IsFalse(JsonParser.Parse("false").AsBoolean);
            Assert.IsTrue(JsonParser.Parse("null").IsNull);
        }

        [Test]
        public void Parse_IntegerPrefersLong()
        {
            JsonValue value = JsonParser.Parse("42");
            Assert.IsTrue(value.IsIntegerNumber);
            Assert.AreEqual(42, value.AsLong);
        }

        [Test]
        public void Parse_DecimalBecomesFloat()
        {
            JsonValue value = JsonParser.Parse("3.14");
            Assert.IsFalse(value.IsIntegerNumber);
            Assert.AreEqual(3.14, value.AsDouble, 1e-9);
        }

        [Test]
        public void Parse_ExponentBecomesFloat()
        {
            JsonValue value = JsonParser.Parse("1e3");
            Assert.IsFalse(value.IsIntegerNumber);
            Assert.AreEqual(1000.0, value.AsDouble, 1e-9);
        }

        [Test]
        public void Parse_OverflowingIntegerFallsBackToDouble()
        {
            JsonValue value = JsonParser.Parse("99999999999999999999999999");
            Assert.IsFalse(value.IsIntegerNumber);
        }

        [Test]
        public void Parse_NegativeNumber()
        {
            Assert.AreEqual(-17, JsonParser.Parse("-17").AsLong);
        }

        [Test]
        public void Parse_EscapeSequences()
        {
            JsonValue value = JsonParser.Parse("\"line1\\nline2\\ttab\\\"quote\\\\back\"");
            Assert.AreEqual("line1\nline2\ttab\"quote\\back", value.AsString);
        }

        [Test]
        public void Parse_UnicodeEscape()
        {
            JsonValue value = JsonParser.Parse("\"\\u4e2d\\u6587\"");
            Assert.AreEqual("中文", value.AsString);
        }

        [Test]
        public void Parse_SurrogatePairReconstructsCharacter()
        {
            // U+1F600 (😀) 编码为代理对 \ud83d\ude00
            JsonValue value = JsonParser.Parse("\"\\ud83d\\ude00\"");
            Assert.AreEqual("😀", value.AsString);
        }

        [Test]
        public void Parse_Object()
        {
            JsonValue value = JsonParser.Parse("{\"a\":1,\"b\":\"two\",\"c\":true,\"d\":null}");
            Assert.AreEqual(1, value["a"].AsLong);
            Assert.AreEqual("two", value["b"].AsString);
            Assert.IsTrue(value["c"].AsBoolean);
            Assert.IsTrue(value["d"].IsNull);
        }

        [Test]
        public void Parse_NestedArrayAndObject()
        {
            JsonValue value = JsonParser.Parse("{\"items\":[1,2,{\"x\":3}]}");
            Assert.AreEqual(3, value["items"].Count);
            Assert.AreEqual(3, value["items"][2]["x"].AsLong);
        }

        [Test]
        public void Parse_WhitespaceIsIgnoredBetweenTokens()
        {
            JsonValue value = JsonParser.Parse("  {  \"a\" : 1 ,  \"b\" : [ 1 , 2 ]  }  ");
            Assert.AreEqual(1, value["a"].AsLong);
            Assert.AreEqual(2, value["b"].Count);
        }

        [Test]
        public void Parse_EmptyObjectAndArray()
        {
            Assert.AreEqual(0, JsonParser.Parse("{}").Count);
            Assert.AreEqual(0, JsonParser.Parse("[]").Count);
        }

        [Test]
        public void Parse_DepthAtLimitSucceeds()
        {
            string json = BuildNestedArray(JsonParser.MaxDepth);
            Assert.DoesNotThrow(() => JsonParser.Parse(json));
        }

        [Test]
        public void Parse_DepthBeyondLimitThrows()
        {
            string json = BuildNestedArray(JsonParser.MaxDepth + 1);
            JsonParseException ex = Assert.Throws<JsonParseException>(() => JsonParser.Parse(json));
            StringAssert.Contains("嵌套深度", ex.Message);
        }

        [Test]
        public void Parse_InputTooLargeThrows()
        {
            string huge = "\"" + new string('a', JsonParser.MaxInputSizeBytes + 1) + "\"";
            JsonParseException ex = Assert.Throws<JsonParseException>(() => JsonParser.Parse(huge));
            StringAssert.Contains("超过上限", ex.Message);
        }

        [Test]
        public void Parse_TrailingGarbageThrowsWithPosition()
        {
            JsonParseException ex = Assert.Throws<JsonParseException>(() => JsonParser.Parse("{}garbage"));
            Assert.AreEqual(2, ex.Position);
        }

        [Test]
        public void Parse_UnterminatedStringThrows()
        {
            Assert.Throws<JsonParseException>(() => JsonParser.Parse("\"abc"));
        }

        [Test]
        public void Parse_TrailingCommaThrows()
        {
            Assert.Throws<JsonParseException>(() => JsonParser.Parse("[1,2,]"));
        }

        [Test]
        public void Parse_MissingColonThrows()
        {
            Assert.Throws<JsonParseException>(() => JsonParser.Parse("{\"a\" 1}"));
        }

        [Test]
        public void Parse_NonStringKeyThrows()
        {
            Assert.Throws<JsonParseException>(() => JsonParser.Parse("{1:2}"));
        }

        [Test]
        public void Parse_ControlCharacterInStringThrows()
        {
            string json = "\"abc\ndef\"";
            Assert.Throws<JsonParseException>(() => JsonParser.Parse(json));
        }

        [Test]
        public void TryParse_ReturnsFalseAndErrorForMalformedInput()
        {
            bool success = JsonParser.TryParse("{not valid", out JsonValue value, out string error);
            Assert.IsFalse(success);
            Assert.IsNull(value);
            Assert.IsNotNull(error);
        }

        private static string BuildNestedArray(int depth)
        {
            StringBuilder builder = new StringBuilder();
            for (int i = 0; i < depth; i++)
            {
                builder.Append('[');
            }

            builder.Append('1');
            for (int i = 0; i < depth; i++)
            {
                builder.Append(']');
            }

            return builder.ToString();
        }
    }
}
