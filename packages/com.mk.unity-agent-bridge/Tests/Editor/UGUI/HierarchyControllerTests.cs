using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Hierarchy;
using Mk.UnityAgentBridge.Editor.Json;
using Mk.UnityAgentBridge.Editor.Routing;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Tests.Hierarchy
{
    public sealed class HierarchyControllerTests
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

        private static BridgeRequestContext MakeContext(Dictionary<string, string> query)
        {
            return BridgeRequestContext.ForTests(query: query);
        }

        [Test]
        public void Find_UnderRoot_MatchesByComponentType()
        {
            GameObject root = Spawn("HierarchyControllerTests_FindRoot");
            GameObject withButton = Spawn("WithButton", root.transform);
            withButton.AddComponent<Button>();
            Spawn("WithoutButton", root.transform);

            JsonValue response = (JsonValue)HierarchyController.Find(MakeContext(new Dictionary<string, string>
            {
                ["under"] = NodePath.BuildPath(root.transform),
                ["component"] = "Button"
            }));

            Assert.IsTrue(response["ok"].AsBoolean);
            Assert.AreEqual(1, response["matchedCount"].AsInt);
            Assert.AreEqual("WithButton", response["nodes"][0]["name"].AsString);
        }

        [Test]
        public void Find_CountOnly_ReturnsCountWithoutNodes()
        {
            GameObject root = Spawn("HierarchyControllerTests_CountRoot");
            Spawn("A", root.transform);
            Spawn("B", root.transform);

            JsonValue response = (JsonValue)HierarchyController.Find(MakeContext(new Dictionary<string, string>
            {
                ["under"] = NodePath.BuildPath(root.transform),
                ["countOnly"] = "true"
            }));

            Assert.AreEqual(2, response["matchedCount"].AsInt);
            Assert.IsFalse(response.ContainsKey("nodes"));
        }

        [Test]
        public void Find_SortByDescWithPageSizeOne_ReturnsTopMatch()
        {
            GameObject root = Spawn("HierarchyControllerTests_SortRoot");
            GameObject low = Spawn("LowCanvas", root.transform);
            low.AddComponent<Canvas>().sortingOrder = 1;
            GameObject high = Spawn("HighCanvas", root.transform);
            high.AddComponent<Canvas>().sortingOrder = 9;
            GameObject mid = Spawn("MidCanvas", root.transform);
            mid.AddComponent<Canvas>().sortingOrder = 5;

            JsonValue response = (JsonValue)HierarchyController.Find(MakeContext(new Dictionary<string, string>
            {
                ["under"] = NodePath.BuildPath(root.transform),
                ["component"] = "Canvas",
                ["sortBy"] = "Canvas.sortingOrder",
                ["order"] = "desc",
                ["pageSize"] = "1"
            }));

            Assert.AreEqual(3, response["matchedCount"].AsInt);
            Assert.AreEqual(1, response["nodes"].Count);
            Assert.AreEqual("HighCanvas", response["nodes"][0]["name"].AsString);
            Assert.IsTrue(response["truncated"].AsBoolean);
            Assert.IsFalse(response["nextCursor"].IsNull);
        }

        [Test]
        public void Find_Pagination_SecondPageContinuesFromCursor()
        {
            GameObject root = Spawn("HierarchyControllerTests_PageRoot");
            Spawn("Alpha", root.transform);
            Spawn("Beta", root.transform);
            Spawn("Gamma", root.transform);

            JsonValue firstPage = (JsonValue)HierarchyController.Find(MakeContext(new Dictionary<string, string>
            {
                ["under"] = NodePath.BuildPath(root.transform),
                ["pageSize"] = "2"
            }));

            Assert.AreEqual(2, firstPage["nodes"].Count);
            Assert.IsTrue(firstPage["truncated"].AsBoolean);
            string cursor = firstPage["nextCursor"].AsString;

            JsonValue secondPage = (JsonValue)HierarchyController.Find(MakeContext(new Dictionary<string, string>
            {
                ["under"] = NodePath.BuildPath(root.transform),
                ["pageSize"] = "2",
                ["cursor"] = cursor
            }));

            Assert.AreEqual(1, secondPage["nodes"].Count);
            Assert.IsFalse(secondPage["truncated"].AsBoolean);
        }

        [Test]
        public void Find_InvalidRegex_ReturnsInvalidArgument()
        {
            object result = HierarchyController.Find(MakeContext(new Dictionary<string, string>
            {
                ["nameRegex"] = "("
            }));

            BridgeResponse response = (BridgeResponse)result;
            Assert.IsFalse(response.ok);
            Assert.AreEqual("invalid_argument", response.code);
        }

        [Test]
        public void Find_UnknownComponent_ReturnsUnknownComponent()
        {
            object result = HierarchyController.Find(MakeContext(new Dictionary<string, string>
            {
                ["component"] = "ThisComponentDoesNotExist"
            }));

            BridgeResponse response = (BridgeResponse)result;
            Assert.IsFalse(response.ok);
            Assert.AreEqual("unknown_component", response.code);
        }

        [Test]
        public void Tree_DepthLimitsDescendants()
        {
            GameObject root = Spawn("HierarchyControllerTests_TreeRoot");
            GameObject depth1 = Spawn("Depth1", root.transform);
            GameObject depth2 = Spawn("Depth2", depth1.transform);
            Spawn("Depth3", depth2.transform);

            JsonValue response = (JsonValue)HierarchyController.Tree(MakeContext(new Dictionary<string, string>
            {
                ["path"] = NodePath.BuildPath(root.transform),
                ["depth"] = "1"
            }));

            Assert.IsTrue(response["ok"].AsBoolean);
            // root(0) + Depth1(1) = 2 nodes within depth<=1；Depth2/Depth3 超出深度不包含。
            Assert.AreEqual(2, response["nodes"].Count);
        }

        [Test]
        public void Tree_UnknownPath_ReturnsNodeNotFound()
        {
            object result = HierarchyController.Tree(MakeContext(new Dictionary<string, string>
            {
                ["path"] = "DoesNotExist"
            }));

            BridgeResponse response = (BridgeResponse)result;
            Assert.IsFalse(response.ok);
            Assert.AreEqual("node_not_found", response.code);
        }

        [Test]
        public void Ancestors_ReturnsNearToFarOrder()
        {
            GameObject grandparent = Spawn("HierarchyControllerTests_Grandparent");
            GameObject parent = Spawn("Parent", grandparent.transform);
            GameObject child = Spawn("Child", parent.transform);

            JsonValue response = (JsonValue)HierarchyController.Ancestors(MakeContext(new Dictionary<string, string>
            {
                ["path"] = NodePath.BuildPath(child.transform)
            }));

            Assert.AreEqual(2, response["ancestors"].Count);
            Assert.AreEqual("Parent", response["ancestors"][0]["name"].AsString);
            Assert.AreEqual("HierarchyControllerTests_Grandparent", response["ancestors"][1]["name"].AsString);
        }

        [Test]
        public void Ancestors_WithComponentFilter_OnlyReturnsMatchingAncestors()
        {
            GameObject grandparent = Spawn("HierarchyControllerTests_GrandparentWithCanvas");
            grandparent.AddComponent<Canvas>();
            GameObject parent = Spawn("ParentNoCanvas", grandparent.transform);
            GameObject child = Spawn("ChildTarget", parent.transform);

            JsonValue response = (JsonValue)HierarchyController.Ancestors(MakeContext(new Dictionary<string, string>
            {
                ["path"] = NodePath.BuildPath(child.transform),
                ["component"] = "Canvas"
            }));

            Assert.AreEqual(1, response["ancestors"].Count);
            Assert.AreEqual("HierarchyControllerTests_GrandparentWithCanvas", response["ancestors"][0]["name"].AsString);
        }

        [Test]
        public void Inspect_ReturnsComponentsWithEffectiveInteractable()
        {
            GameObject go = Spawn("HierarchyControllerTests_Inspect");
            Button button = go.AddComponent<Button>();
            button.interactable = true;

            JsonValue response = (JsonValue)HierarchyController.Inspect(MakeContext(new Dictionary<string, string>
            {
                ["path"] = NodePath.BuildPath(go.transform)
            }));

            Assert.IsTrue(response["ok"].AsBoolean);
            JsonValue node = response["node"];
            Assert.IsTrue(node["effectiveInteractable"].AsBoolean);
            Assert.IsTrue(node["components"].Count >= 2); // Transform + Button（至少）
            Assert.IsTrue(node.ContainsKey("serializationErrors"));
        }
    }
}
