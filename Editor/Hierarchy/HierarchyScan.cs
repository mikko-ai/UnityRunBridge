using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Mk.UnityAgentBridge.Editor.Hierarchy
{
    /// <summary>
    /// 场景枚举的唯一实现：所有 hierarchy 端点与 NodePath 解析都必须走这里，
    /// 保证 DontDestroyOnLoad 的枚举方式全项目只有一处。
    /// </summary>
    internal static class HierarchyScan
    {
        public sealed class SceneRoots
        {
            public string SceneName;
            public bool IsLoaded;
            public List<Transform> Roots;
        }

        public static List<SceneRoots> GetAllScenesWithRoots()
        {
            List<SceneRoots> result = new List<SceneRoots>();
            for (int i = 0; i < SceneManager.sceneCount; i++)
            {
                Scene scene = SceneManager.GetSceneAt(i);
                List<Transform> roots = new List<Transform>();
                if (scene.isLoaded)
                {
                    foreach (GameObject go in scene.GetRootGameObjects())
                    {
                        roots.Add(go.transform);
                    }
                }

                result.Add(new SceneRoots { SceneName = scene.name, IsLoaded = scene.isLoaded, Roots = roots });
            }

            List<Transform> ddolRoots = GetDontDestroyOnLoadRoots();
            if (ddolRoots.Count > 0)
            {
                result.Add(new SceneRoots
                {
                    SceneName = NodePath.DontDestroyOnLoadSceneName,
                    IsLoaded = true,
                    Roots = ddolRoots
                });
            }

            return result;
        }

        /// <summary>
        /// DDOL 场景不被 SceneManager 枚举，唯一取得其句柄的办法是临时挂一个对象上去再读
        /// 它所在的 scene。仅在 Play Mode 下有意义（Edit Mode 没有 DontDestroyOnLoad 场景）。
        /// </summary>
        public static List<Transform> GetDontDestroyOnLoadRoots()
        {
            List<Transform> roots = new List<Transform>();
            if (!Application.isPlaying)
            {
                return roots;
            }

            GameObject probe = new GameObject("~UnityAgentBridgeDdolProbe")
            {
                hideFlags = HideFlags.HideAndDontSave
            };

            try
            {
                Object.DontDestroyOnLoad(probe);
                Scene ddolScene = probe.scene;
                foreach (GameObject go in ddolScene.GetRootGameObjects())
                {
                    if (go != probe)
                    {
                        roots.Add(go.transform);
                    }
                }
            }
            finally
            {
                Object.DestroyImmediate(probe);
            }

            return roots;
        }

        public static List<Transform> GetChildren(Transform parent)
        {
            List<Transform> children = new List<Transform>(parent.childCount);
            for (int i = 0; i < parent.childCount; i++)
            {
                children.Add(parent.GetChild(i));
            }

            return children;
        }
    }
}
