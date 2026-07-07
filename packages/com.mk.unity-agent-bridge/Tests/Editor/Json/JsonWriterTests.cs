using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Json
{
    public sealed class JsonWriterTests
    {
        [Test]
        public void Serialize_Primitives()
        {
            Assert.AreEqual("null", JsonWriter.Serialize(null));
            Assert.AreEqual("true", JsonWriter.Serialize(true));
            Assert.AreEqual("false", JsonWriter.Serialize(false));
            Assert.AreEqual("42", JsonWriter.Serialize(42));
            Assert.AreEqual("42", JsonWriter.Serialize(42L));
            Assert.AreEqual("\"hi\"", JsonWriter.Serialize("hi"));
        }

        [Test]
        public void Serialize_FloatKeepsDecimalMarker()
        {
            Assert.AreEqual("4.0", JsonWriter.Serialize(4.0));
            Assert.AreEqual("3.14", JsonWriter.Serialize(3.14));
        }

        [Test]
        public void Serialize_RejectsNaNAndInfinity()
        {
            Assert.Throws<JsonWriterException>(() => JsonWriter.Serialize(double.NaN));
            Assert.Throws<JsonWriterException>(() => JsonWriter.Serialize(double.PositiveInfinity));
            Assert.Throws<JsonWriterException>(() => JsonWriter.Serialize(double.NegativeInfinity));
        }

        [Test]
        public void Serialize_Dictionary_ProducesObject()
        {
            Dictionary<string, object> payload = new Dictionary<string, object>
            {
                ["ok"] = true,
                ["count"] = 3
            };

            string json = JsonWriter.Serialize(payload);
            JsonValue parsed = JsonParser.Parse(json);
            Assert.IsTrue(parsed["ok"].AsBoolean);
            Assert.AreEqual(3, parsed["count"].AsLong);
        }

        [Test]
        public void Serialize_List_ProducesArray()
        {
            List<object> payload = new List<object> { 1, "two", false };
            string json = JsonWriter.Serialize(payload);
            Assert.AreEqual("[1,\"two\",false]", json);
        }

        [Test]
        public void Serialize_EscapesControlCharactersAndQuotes()
        {
            string raw = "line1\nline2\ttab\"quote\\back\bbksp\fform\rcr";
            string json = JsonWriter.Serialize(raw);

            Assert.AreEqual(
                "\"line1\\nline2\\ttab\\\"quote\\\\back\\bbksp\\fform\\rcr\"",
                json
            );
        }

        [Test]
        public void Serialize_EscapesLowControlCharAsUnicode()
        {
            string raw = "a\u0001b";
            string json = JsonWriter.Serialize(raw);
            Assert.AreEqual("\"a\\u0001b\"", json);
        }

        [Test]
        public void Serialize_UnsupportedType_Throws()
        {
            Assert.Throws<JsonWriterException>(() => JsonWriter.Serialize(new System.Text.StringBuilder()));
        }

        [Test]
        public void Serialize_EnumWritesName()
        {
            Assert.AreEqual("\"Number\"", JsonWriter.Serialize(JsonValueType.Number));
        }

        [Test]
        public void RoundTrip_NestedStructure()
        {
            JsonValue root = JsonValue.NewObject();
            root["ok"] = true;
            root["name"] = "BuyButton";
            root["score"] = 3.5;
            JsonValue array = JsonValue.NewArray();
            array.Add("a");
            array.Add(1);
            root["items"] = array;

            string json = JsonWriter.Serialize(root);
            JsonValue parsed = JsonParser.Parse(json);

            Assert.IsTrue(parsed["ok"].AsBoolean);
            Assert.AreEqual("BuyButton", parsed["name"].AsString);
            Assert.AreEqual(3.5, parsed["score"].AsDouble);
            Assert.AreEqual("a", parsed["items"][0].AsString);
            Assert.AreEqual(1, parsed["items"][1].AsLong);
        }
    }
}
