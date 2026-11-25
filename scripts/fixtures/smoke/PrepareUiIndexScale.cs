using System;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;

// Test-only importer controls. Never distributed with the Bridge.
[InitializeOnLoad]
public static class PrepareUiIndexScale
{
    private const string Request = "ui-index-scale-request.txt";
    private const string Reply = "ui-index-scale-reply.txt";

    static PrepareUiIndexScale() => EditorApplication.update += ChangeOnce;

    public static void Setup()
    {
        foreach (int count in new[] { 10, 100, 1000 })
        {
            string root = "Assets/Bench" + count;
            AssetDatabase.CreateFolder("Assets", "Bench" + count);
            var loose = MakeButton("Loose");
            if (PrefabUtility.SaveAsPrefabAsset(loose, root + "/Loose.prefab") == null)
                throw new InvalidOperationException("Could not save loose prefab");
            UnityEngine.Object.DestroyImmediate(loose);
            var source = MakeButton("Base");
            var template = PrefabUtility.SaveAsPrefabAsset(source, root + "/Base.prefab");
            UnityEngine.Object.DestroyImmediate(source);
            var container = new GameObject("Dependent", typeof(RectTransform));
            PrefabUtility.InstantiatePrefab(template, container.transform);
            if (PrefabUtility.SaveAsPrefabAsset(container, root + "/Dependent.prefab") == null)
                throw new InvalidOperationException("Could not save dependent prefab");
            UnityEngine.Object.DestroyImmediate(container);
            for (int n = 3; n < count; n++)
                File.Copy(root + "/Loose.prefab", root + "/Extra-" + n + ".prefab");
        }
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        File.WriteAllText("game-view-ready.txt", "ready");
    }

    private static GameObject MakeButton(string name) =>
        new GameObject(name, typeof(RectTransform), typeof(Image), typeof(Button));

    private static void ChangeOnce()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isUpdating
            || EditorApplication.isCompiling || !File.Exists(Request))
            return;
        string request = File.ReadAllText(Request);
        File.Delete(Request);
        string reply = "ok";
        try
        {
            string[] parts = request.Split(':');
            if (parts.Length != 2 || !int.TryParse(parts[0], out int size)
                || (size != 10 && size != 100 && size != 1000)
                || (parts[1] != "Loose" && parts[1] != "Base"))
                throw new ArgumentException("Unknown fixture mutation");
            string path = "Assets/Bench" + size + "/" + parts[1] + ".prefab";
            var contents = PrefabUtility.LoadPrefabContents(path);
            try
            {
                var button = contents.GetComponent<Button>();
                button.interactable = !button.interactable;
                if (PrefabUtility.SaveAsPrefabAsset(contents, path) == null)
                    throw new InvalidOperationException("Could not save fixture mutation");
            }
            finally { PrefabUtility.UnloadPrefabContents(contents); }
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        }
        catch (Exception ex) { reply = ex.ToString(); }
        File.WriteAllText(Reply + ".pending", reply);
        File.Move(Reply + ".pending", Reply);
    }
}
