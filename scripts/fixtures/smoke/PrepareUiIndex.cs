using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;

public static class PrepareUiIndex
{
    public static void Setup()
    {
        AssetDatabase.CreateFolder("Assets", "Menu");
        var panel = new GameObject("Menu", typeof(RectTransform));
        try
        {
            var button = new GameObject("Open Test Panel", typeof(RectTransform), typeof(Image), typeof(Button));
            button.transform.SetParent(panel.transform, false);
            if (PrefabUtility.SaveAsPrefabAsset(panel, "Assets/Menu/Menu.prefab") == null)
                throw new System.InvalidOperationException("Could not prepare UI index prefab.");
        }
        finally
        {
            Object.DestroyImmediate(panel);
        }
        File.WriteAllText("game-view-ready.txt", "ready");
    }
}
