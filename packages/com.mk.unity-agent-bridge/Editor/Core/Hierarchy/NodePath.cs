using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Mk.UnityAgentBridge.Editor.Hierarchy
{
    /// <summary>
    /// path 生成与解析必须互逆，因此放在同一个类里维护。
    ///
    /// 生成规则：从场景根到目标节点用 "/" 拼接 name；同一父节点（或同一场景的根层）下
    /// 出现重名兄弟时，所有同名节点都追加 "[index]"（index 是该名字重名分组内的 0-based
    /// 序号，遍历顺序 = Transform 兄弟顺序）；不重名则不追加。
    /// </summary>
    public static class NodePath
    {
        public const string DontDestroyOnLoadSceneName = "DontDestroyOnLoad";

        private static readonly Regex SegmentPattern = new Regex(@"^(?<name>.*)\[(?<index>\d+)\]$", RegexOptions.Compiled);

        public struct PathSegment
        {
            public string Name;
            public int? Index;
        }

        public sealed class ResolveResult
        {
            public bool Ok;
            public Transform Node;
            public string Scene;
            public string ErrorCode;
            public string ErrorMessage;
            public List<string> AmbiguousScenes;

            public static ResolveResult Success(Transform node, string scene)
            {
                return new ResolveResult { Ok = true, Node = node, Scene = scene };
            }

            public static ResolveResult Fail(string errorCode, string errorMessage)
            {
                return new ResolveResult { Ok = false, ErrorCode = errorCode, ErrorMessage = errorMessage };
            }

            public static ResolveResult AmbiguousPath(List<string> candidateScenes)
            {
                return new ResolveResult
                {
                    Ok = false,
                    ErrorCode = "ambiguous_path",
                    ErrorMessage = "path 在多个已加载场景中命中，候选场景：" + string.Join(", ", candidateScenes),
                    AmbiguousScenes = candidateScenes
                };
            }
        }

        public static string GetSceneDisplayName(GameObject go)
        {
            string name = go.scene.name;
            return string.IsNullOrEmpty(name) ? DontDestroyOnLoadSceneName : name;
        }

        public static string BuildPath(Transform transform)
        {
            List<string> segments = new List<string>();
            Transform current = transform;
            while (current != null)
            {
                segments.Insert(0, BuildSegment(current));
                current = current.parent;
            }

            return string.Join("/", segments);
        }

        private static string BuildSegment(Transform node)
        {
            IReadOnlyList<Transform> siblings = node.parent != null
                ? HierarchyScan.GetChildren(node.parent)
                : GetSceneRoots(node.gameObject.scene);

            int sameNameCount = 0;
            int myIndex = -1;
            for (int i = 0; i < siblings.Count; i++)
            {
                if (siblings[i].name != node.name)
                {
                    continue;
                }

                if (siblings[i] == node)
                {
                    myIndex = sameNameCount;
                }

                sameNameCount++;
            }

            return sameNameCount > 1 ? $"{node.name}[{myIndex}]" : node.name;
        }

        private static List<Transform> GetSceneRoots(Scene scene)
        {
            List<Transform> roots = new List<Transform>();
            foreach (GameObject go in scene.GetRootGameObjects())
            {
                roots.Add(go.transform);
            }

            return roots;
        }

        public static List<PathSegment> ParseSegments(string path)
        {
            List<PathSegment> segments = new List<PathSegment>();
            foreach (string raw in path.Split('/'))
            {
                if (raw.Length == 0)
                {
                    continue;
                }

                Match match = SegmentPattern.Match(raw);
                segments.Add(match.Success
                    ? new PathSegment { Name = match.Groups["name"].Value, Index = int.Parse(match.Groups["index"].Value) }
                    : new PathSegment { Name = raw, Index = null });
            }

            return segments;
        }

        private static Transform FindAmong(IReadOnlyList<Transform> candidates, PathSegment segment)
        {
            if (segment.Index.HasValue)
            {
                int count = 0;
                foreach (Transform candidate in candidates)
                {
                    if (candidate.name != segment.Name)
                    {
                        continue;
                    }

                    if (count == segment.Index.Value)
                    {
                        return candidate;
                    }

                    count++;
                }

                return null;
            }

            foreach (Transform candidate in candidates)
            {
                if (candidate.name == segment.Name)
                {
                    return candidate;
                }
            }

            return null;
        }

        /// <summary>纯数字视为 instanceId；否则按 path 解析。</summary>
        public static ResolveResult Resolve(string pathOrInstanceId, string sceneFilter)
        {
            if (string.IsNullOrWhiteSpace(pathOrInstanceId))
            {
                return ResolveResult.Fail("invalid_argument", "path or instanceId is required");
            }

            if (int.TryParse(pathOrInstanceId, NumberStyles.Integer, CultureInfo.InvariantCulture, out int instanceId))
            {
                GameObject go = EditorUtility.InstanceIDToObject(instanceId) as GameObject;
                if (go == null)
                {
                    return ResolveResult.Fail("node_not_found", $"instanceId 未找到：{instanceId}");
                }

                return ResolveResult.Success(go.transform, GetSceneDisplayName(go));
            }

            List<PathSegment> segments = ParseSegments(pathOrInstanceId);
            if (segments.Count == 0)
            {
                return ResolveResult.Fail("invalid_argument", "path 不能为空");
            }

            List<HierarchyScan.SceneRoots> allScenes = HierarchyScan.GetAllScenesWithRoots();
            List<(string Scene, Transform Node)> matches = new List<(string, Transform)>();

            foreach (HierarchyScan.SceneRoots sceneRoots in allScenes)
            {
                if (!sceneRoots.IsLoaded)
                {
                    continue;
                }

                if (!string.IsNullOrEmpty(sceneFilter) &&
                    !string.Equals(sceneRoots.SceneName, sceneFilter, System.StringComparison.Ordinal))
                {
                    continue;
                }

                Transform current = FindAmong(sceneRoots.Roots, segments[0]);
                for (int i = 1; current != null && i < segments.Count; i++)
                {
                    current = FindAmong(HierarchyScan.GetChildren(current), segments[i]);
                }

                if (current != null)
                {
                    matches.Add((sceneRoots.SceneName, current));
                }
            }

            if (matches.Count == 0)
            {
                return ResolveResult.Fail("node_not_found", $"未找到路径：{pathOrInstanceId}");
            }

            if (matches.Count > 1 && string.IsNullOrEmpty(sceneFilter))
            {
                List<string> candidateScenes = new List<string>();
                foreach ((string scene, Transform _) in matches)
                {
                    candidateScenes.Add(scene);
                }

                return ResolveResult.AmbiguousPath(candidateScenes);
            }

            (string resolvedScene, Transform resolvedNode) = matches[0];
            return ResolveResult.Success(resolvedNode, resolvedScene);
        }
    }
}
