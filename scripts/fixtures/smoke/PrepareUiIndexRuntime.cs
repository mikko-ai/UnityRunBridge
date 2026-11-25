using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

public static class PrepareUiIndexRuntime
{
    public static void Setup()
    {
        // Reuse the 2022.3-only fixture Game View setup. The runtime scene below
        // is independent of UiReviewDemo and uses a serialized Prefab instance.
        PrepareGameView.Setup();
        var other = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        if (!EditorSceneManager.SaveScene(other, "Assets/Scenes/Other.unity"))
            throw new System.InvalidOperationException("Could not save alternate fixture scene");
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        AssetDatabase.CreateFolder("Assets", "Menu");
        var panel = new GameObject("Panel", typeof(RectTransform));
        AddButton("Action", panel.transform, new Vector2(-80, 0));
        AddButton("Action", panel.transform, new Vector2(80, 0));
        var template = PrefabUtility.SaveAsPrefabAsset(panel, "Assets/Menu/Panel.prefab");
        Object.DestroyImmediate(panel);
        new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));
        var camera = new GameObject("Camera", typeof(Camera)).GetComponent<Camera>();
        camera.clearFlags = CameraClearFlags.SolidColor;
        var canvas = new GameObject("UiCanvas", typeof(RectTransform), typeof(Canvas), typeof(GraphicRaycaster));
        canvas.GetComponent<Canvas>().renderMode = RenderMode.ScreenSpaceOverlay;
        var instance = (GameObject)PrefabUtility.InstantiatePrefab(template, canvas.transform);
        var harness = new GameObject("Probe").AddComponent<UiIndexFixtureProbe>();
        harness.prefabRoot = instance.transform;
        harness.expected = instance.transform.GetChild(0).GetComponent<Button>();
        harness.other = instance.transform.GetChild(1).GetComponent<Button>();
        harness.dynamic = AddButton("Dynamic", canvas.transform, new Vector2(0, 85));
        var cover = new GameObject("Cover", typeof(RectTransform), typeof(Image));
        var rect = cover.GetComponent<RectTransform>();
        rect.SetParent(canvas.transform, false);
        rect.sizeDelta = new Vector2(300, 60);
        cover.SetActive(false);
        harness.cover = cover;
        if (!EditorSceneManager.SaveScene(scene, "Assets/Scenes/Indexed.unity"))
            throw new System.InvalidOperationException("Could not save fixture scene");
        UiIndexFixtureProbe.LogIdentity("EDIT", instance);
        UiIndexFixtureProbe.LogIdentity("EDIT-COMPONENT", harness.expected);
    }

    private static Button AddButton(string name, Transform parent, Vector2 position)
    {
        var node = new GameObject(name, typeof(RectTransform), typeof(Image), typeof(Button));
        var rect = node.GetComponent<RectTransform>();
        rect.SetParent(parent, false);
        rect.anchoredPosition = position;
        rect.sizeDelta = new Vector2(105, 52);
        return node.GetComponent<Button>();
    }
}
