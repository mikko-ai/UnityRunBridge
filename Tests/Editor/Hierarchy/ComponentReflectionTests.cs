using Mk.UnityAgentBridge.Editor.Hierarchy;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Tests.Hierarchy
{
    public sealed class ComponentReflectionTests
    {
        [Test]
        public void TryParseMemberPath_SplitsOnLastDot()
        {
            bool ok = ComponentReflection.TryParseMemberPath("UnityEngine.UI.Selectable.interactable", out string component, out string member);

            Assert.IsTrue(ok);
            Assert.AreEqual("UnityEngine.UI.Selectable", component);
            Assert.AreEqual("interactable", member);
        }

        [Test]
        public void TryParseMemberPath_NoDot_ReturnsFalse()
        {
            Assert.IsFalse(ComponentReflection.TryParseMemberPath("NoDotHere", out _, out _));
        }

        [TestCase("Canvas.sortingOrder=5", "Canvas.sortingOrder", "=", "5")]
        [TestCase("Canvas.sortingOrder!=5", "Canvas.sortingOrder", "!=", "5")]
        [TestCase("Canvas.sortingOrder>=5", "Canvas.sortingOrder", ">=", "5")]
        [TestCase("Canvas.sortingOrder<=5", "Canvas.sortingOrder", "<=", "5")]
        [TestCase("Canvas.sortingOrder>5", "Canvas.sortingOrder", ">", "5")]
        [TestCase("Canvas.sortingOrder<5", "Canvas.sortingOrder", "<", "5")]
        public void TryParseWhereExpression_AllOperators(string expression, string expectedMemberPath, string expectedOp, string expectedLiteral)
        {
            bool ok = ComponentReflection.TryParseWhereExpression(expression, out string memberPath, out string op, out string literal);

            Assert.IsTrue(ok);
            Assert.AreEqual(expectedMemberPath, memberPath);
            Assert.AreEqual(expectedOp, op);
            Assert.AreEqual(expectedLiteral, literal);
        }

        [Test]
        public void TryGetMemberValue_ReadsInheritedProperty()
        {
            GameObject go = new GameObject("ComponentReflectionTests_Value");
            try
            {
                Button button = go.AddComponent<Button>();
                button.interactable = true;

                bool ok = ComponentReflection.TryGetMemberValue(go, typeof(Selectable), "interactable", out object value, out string error);

                Assert.IsTrue(ok, error);
                Assert.AreEqual(true, value);
            }
            finally
            {
                Object.DestroyImmediate(go);
            }
        }

        [Test]
        public void TryGetMemberValue_ComponentNotPresent_ReturnsFalse()
        {
            GameObject go = new GameObject("ComponentReflectionTests_Missing");
            try
            {
                bool ok = ComponentReflection.TryGetMemberValue(go, typeof(Button), "interactable", out _, out _);
                Assert.IsFalse(ok);
            }
            finally
            {
                Object.DestroyImmediate(go);
            }
        }

        [Test]
        public void TryCompare_NumericGreaterThan()
        {
            bool ok = ComponentReflection.TryCompare(10, ">", "5", out bool matches, out string error);
            Assert.IsTrue(ok, error);
            Assert.IsTrue(matches);
        }

        [Test]
        public void TryCompare_BoolOnlySupportsEquality()
        {
            bool ok = ComponentReflection.TryCompare(true, ">", "false", out _, out string error);
            Assert.IsFalse(ok);
            Assert.IsNotNull(error);
        }

        [Test]
        public void TryCompare_StringEquality()
        {
            bool ok = ComponentReflection.TryCompare("hello", "=", "hello", out bool matches, out _);
            Assert.IsTrue(ok);
            Assert.IsTrue(matches);
        }

        [Test]
        public void GetSortKey_NumericValue_ReturnsComparableDouble()
        {
            System.IComparable key = ComponentReflection.GetSortKey(5);
            Assert.AreEqual(5.0, key);
        }

        [Test]
        public void GetSortKey_NullValue_ReturnsNull()
        {
            Assert.IsNull(ComponentReflection.GetSortKey(null));
        }
    }
}
