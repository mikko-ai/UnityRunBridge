using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Json
{
    public sealed class JsonValueTests
    {
        [Test]
        public void NewObject_PreservesInsertionOrder()
        {
            JsonValue obj = JsonValue.NewObject();
            obj["z"] = 1;
            obj["a"] = 2;
            obj["m"] = 3;

            CollectionAssert.AreEqual(new[] { "z", "a", "m" }, obj.Keys);
        }

        [Test]
        public void Indexer_Set_OverwritesWithoutChangingOrder()
        {
            JsonValue obj = JsonValue.NewObject();
            obj["a"] = 1;
            obj["b"] = 2;
            obj["a"] = 99;

            CollectionAssert.AreEqual(new[] { "a", "b" }, obj.Keys);
            Assert.AreEqual(99, obj["a"].AsLong);
        }

        [Test]
        public void Indexer_Get_MissingKeyReturnsNull()
        {
            JsonValue obj = JsonValue.NewObject();
            Assert.IsTrue(obj["missing"].IsNull);
        }

        [Test]
        public void Array_AddAndIndex()
        {
            JsonValue array = JsonValue.NewArray();
            array.Add(1);
            array.Add("two");
            array.Add(true);

            Assert.AreEqual(3, array.Count);
            Assert.AreEqual(1, array[0].AsLong);
            Assert.AreEqual("two", array[1].AsString);
            Assert.IsTrue(array[2].AsBoolean);
        }

        [Test]
        public void ImplicitConversions_CreateExpectedTypes()
        {
            JsonValue boolValue = true;
            JsonValue intValue = 42;
            JsonValue doubleValue = 3.14;
            JsonValue stringValue = "hi";

            Assert.IsTrue(boolValue.IsBoolean);
            Assert.IsTrue(intValue.IsNumber);
            Assert.IsTrue(intValue.IsIntegerNumber);
            Assert.IsTrue(doubleValue.IsNumber);
            Assert.IsTrue(stringValue.IsString);
        }

        [Test]
        public void TryGetHelpers_ReturnFalseForWrongType()
        {
            JsonValue obj = JsonValue.NewObject();
            obj["name"] = "bob";

            Assert.IsFalse(obj.TryGetLong("name", out _));
            Assert.IsTrue(obj.TryGetString("name", out string value));
            Assert.AreEqual("bob", value);
        }

        [Test]
        public void FromDouble_RejectsNaNAndInfinity()
        {
            Assert.Throws<JsonWriterException>(() => JsonValue.FromDouble(double.NaN));
            Assert.Throws<JsonWriterException>(() => JsonValue.FromDouble(double.PositiveInfinity));
        }
    }
}
