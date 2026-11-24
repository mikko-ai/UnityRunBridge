using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityRunBridge.Examples;

// Test fixture only. The reflection below is tied to Unity 2022.3's Game View.
[InitializeOnLoad]
internal static class PrepareGameView
{
    private const BindingFlags Members = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
    private const string ScenePath = "Assets/Scenes/UiReview.unity";

    static PrepareGameView() => EditorApplication.delayCall += Setup;

    private static void Setup()
    {
        if (File.Exists("game-view-ready.txt")) return;
        try
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            new GameObject("UiReviewDemo").AddComponent<UiReviewDemo>();
            EditorSceneManager.SaveScene(scene, ScenePath);

            var dimension = File.ReadAllText("game-view-size.txt").Split('x');
            int width = int.Parse(dimension[0]), height = int.Parse(dimension[1]);
            var assembly = typeof(EditorWindow).Assembly;
            var sizesType = assembly.GetType("UnityEditor.GameViewSizes");
            var sizeType = assembly.GetType("UnityEditor.GameViewSize");
            var sizeKind = assembly.GetType("UnityEditor.GameViewSizeType");
            var singleton = typeof(ScriptableSingleton<>).MakeGenericType(sizesType);
            var sizes = singleton.GetProperty("instance", BindingFlags.Public | BindingFlags.Static).GetValue(null);
            var group = sizesType.GetProperty("currentGroup", Members).GetValue(sizes);
            var groupType = group.GetType();
            int index = (int)groupType.GetMethod("GetTotalCount", Members).Invoke(group, null);
            var size = Activator.CreateInstance(sizeType, Members, null,
                new object[] { Enum.Parse(sizeKind, "FixedResolution"), width, height, $"Bridge smoke {width}x{height}" }, null);
            groupType.GetMethod("AddCustomSize", Members).Invoke(group, new[] { size });

            var viewType = assembly.GetType("UnityEditor.GameView");
            var playViewType = assembly.GetType("UnityEditor.PlayModeView");
            foreach (var item in Resources.FindObjectsOfTypeAll(playViewType))
                if (item is EditorWindow window && window.GetType() != viewType) window.Close();
            var view = EditorWindow.GetWindow(viewType);
            view.Show();
            view.Focus();
            viewType.GetMethod("SizeSelectionCallback", Members).Invoke(view, new object[] { index, null });
            view.Repaint();
            WriteMarker("ready");
        }
        catch (Exception ex)
        {
            WriteMarker(ex.ToString());
            Debug.LogException(ex);
        }
    }

    private static void WriteMarker(string message)
    {
        File.WriteAllText("game-view-ready.pending", message);
        File.Move("game-view-ready.pending", "game-view-ready.txt");
    }
}
