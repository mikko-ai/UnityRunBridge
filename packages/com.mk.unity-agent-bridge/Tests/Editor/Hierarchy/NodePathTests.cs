using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using NUnit.Framework;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Tests.Hierarchy
{
    public sealed class NodePathTests
    {
        private readonly List<GameObject> spawned = new List<GameObject>();

        [TearDown]
        public void Cleanup()
        {
            foreach (GameObject go in spawned)
            {
                if (go != null)
                {
                    Object.DestroyImmediate(go);
                }
            }

            spawned.Clear();
        }

        private GameObject Spawn(string name, Transform parent = null)
        {
            GameObject go = new GameObject(name);
            if (parent != null)
            {
                go.transform.SetParent(parent, worldPositionStays: false);
            }

            spawned.Add(go);
            return go;
        }

        [Test]
        public void BuildPath_UniqueNames_NoIndexSuffix()
        {
            GameObject root = Spawn("NodePathTests_UniqueRoot");
            GameObject child = Spawn("Child", root.transform);

            string path = NodePath.BuildPath(child.transform);

            Assert.AreEqual("NodePathTests_UniqueRoot/Child", path);
        }

        [Test]
        public void BuildPath_DuplicateSiblingNames_AppendsIndexToAll()
        {
            GameObject root = Spawn("NodePathTests_DupRoot");
            GameObject first = Spawn("Item", root.transform);
            GameObject second = Spawn("Item", root.transform);
            GameObject third = Spawn("Item", root.transform);

            Assert.AreEqual("NodePathTests_DupRoot/Item[0]", NodePath.BuildPath(first.transform));
            Assert.AreEqual("NodePathTests_DupRoot/Item[1]", NodePath.BuildPath(second.transform));
            Assert.AreEqual("NodePathTests_DupRoot/Item[2]", NodePath.BuildPath(third.transform));
        }

        [Test]
        public void Resolve_RoundTripsWithBuildPath()
        {
            GameObject root = Spawn("NodePathTests_RoundTripRoot");
            GameObject mid = Spawn("Mid", root.transform);
            GameObject leaf = Spawn("Leaf", mid.transform);

            string path = NodePath.BuildPath(leaf.transform);
            NodePath.ResolveResult result = NodePath.Resolve(path, null);

            Assert.IsTrue(result.Ok);
            Assert.AreEqual(leaf.transform, result.Node);
        }

        [Test]
        public void Resolve_DuplicateSiblingPath_ResolvesCorrectIndex()
        {
            GameObject root = Spawn("NodePathTests_DupResolveRoot");
            GameObject first = Spawn("Dup", root.transform);
            GameObject second = Spawn("Dup", root.transform);

            NodePath.ResolveResult resultZero = NodePath.Resolve(NodePath.BuildPath(first.transform), null);
            NodePath.ResolveResult resultOne = NodePath.Resolve(NodePath.BuildPath(second.transform), null);

            Assert.AreEqual(first.transform, resultZero.Node);
            Assert.AreEqual(second.transform, resultOne.Node);
        }

        [Test]
        public void Resolve_ByInstanceId_ReturnsNode()
        {
            GameObject go = Spawn("NodePathTests_ById");

            NodePath.ResolveResult result = NodePath.Resolve(go.GetInstanceID().ToString(), null);

            Assert.IsTrue(result.Ok);
            Assert.AreEqual(go.transform, result.Node);
        }

        [Test]
        public void Resolve_UnknownInstanceId_ReturnsNodeNotFound()
        {
            NodePath.ResolveResult result = NodePath.Resolve("999999999", null);

            Assert.IsFalse(result.Ok);
            Assert.AreEqual("node_not_found", result.ErrorCode);
        }

        [Test]
        public void Resolve_UnknownPath_ReturnsNodeNotFound()
        {
            NodePath.ResolveResult result = NodePath.Resolve("DoesNotExist/AtAll", null);

            Assert.IsFalse(result.Ok);
            Assert.AreEqual("node_not_found", result.ErrorCode);
        }

        [Test]
        public void ParseSegments_MixesPlainAndIndexedSegments()
        {
            List<NodePath.PathSegment> segments = NodePath.ParseSegments("Main/Item[2]/Leaf");

            Assert.AreEqual(3, segments.Count);
            Assert.AreEqual("Main", segments[0].Name);
            Assert.IsNull(segments[0].Index);
            Assert.AreEqual("Item", segments[1].Name);
            Assert.AreEqual(2, segments[1].Index);
            Assert.AreEqual("Leaf", segments[2].Name);
        }
    }
}
