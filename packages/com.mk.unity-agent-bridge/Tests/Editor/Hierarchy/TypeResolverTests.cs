using Mk.UnityAgentBridge.Editor.Hierarchy;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Tests.Hierarchy
{
    public sealed class TypeResolverTests
    {
        [Test]
        public void ResolveComponentType_ShortName_ResolvesUniqueType()
        {
            TypeResolveResult result = TypeResolver.ResolveComponentType("Button");

            Assert.IsTrue(result.Ok);
            Assert.AreEqual(typeof(Button), result.Type);
        }

        [Test]
        public void ResolveComponentType_FullyQualifiedName_Resolves()
        {
            TypeResolveResult result = TypeResolver.ResolveComponentType("UnityEngine.UI.Button");

            Assert.IsTrue(result.Ok);
            Assert.AreEqual(typeof(Button), result.Type);
        }

        [Test]
        public void ResolveComponentType_UnknownName_ReturnsUnknownComponent()
        {
            TypeResolveResult result = TypeResolver.ResolveComponentType("ThisComponentDoesNotExist");

            Assert.IsFalse(result.Ok);
            Assert.AreEqual("unknown_component", result.ErrorCode);
        }

        [Test]
        public void ResolveInterfaceType_ShortName_ResolvesPointerClickHandler()
        {
            TypeResolveResult result = TypeResolver.ResolveInterfaceType("IPointerClickHandler");

            Assert.IsTrue(result.Ok);
            Assert.IsTrue(result.Type.IsInterface);
        }

        [Test]
        public void ComponentMatches_DerivedClassMatchesBaseQuery()
        {
            GameObject go = new GameObject("TypeResolverTests_Derived");
            try
            {
                Button button = go.AddComponent<Button>();
                Assert.IsTrue(TypeResolver.ComponentMatches(typeof(Selectable), button));
            }
            finally
            {
                Object.DestroyImmediate(go);
            }
        }
    }
}
