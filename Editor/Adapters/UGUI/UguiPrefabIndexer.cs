using System;
using System.Collections.Generic;
using System.Globalization;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEditor;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Mk.UnityAgentBridge.Editor.Adapters.UGUI
{
    internal sealed class UguiPrefabIndexer : IUiPrefabIndexer
    {
        private const int MaxControls = 4096;
        private const int MaxPersistentListeners = 64;

        public JsonValue ReadControls(GameObject prefab)
        {
            var controls = JsonValue.NewArray();
            var pending = new Stack<Transform>();
            pending.Push(prefab.transform);
            while (pending.Count > 0)
            {
                Transform node = pending.Pop();
                for (int i = node.childCount - 1; i >= 0; i--)
                    pending.Push(node.GetChild(i));

                if (!(node is RectTransform))
                    continue;
                Component[] components = node.GetComponents<Component>();
                for (int i = 0; i < components.Length; i++)
                {
                    Component component = components[i];
                    if (!(component is Selectable) && !(component is IPointerClickHandler))
                        continue;
                    if (controls.Count == MaxControls)
                        throw new InvalidOperationException("单个 Prefab 的控件数量超出索引上限");

                    var control = JsonValue.NewObject();
                    control["name"] = node.name;
                    control["componentType"] = component.GetType().FullName;
                    control["componentIndex"] = i;
                    control["path"] = RelativePath(prefab.transform, node);
                    control["activeSelf"] = node.gameObject.activeSelf;
                    control["enabled"] = component is Behaviour behaviour && behaviour.enabled;
                    control["interactable"] = component is Selectable selectable
                        ? JsonValue.FromBoolean(selectable.interactable) : JsonValue.Null;
                    control["pointerClickHandler"] = component is IPointerClickHandler;
                    if (AssetDatabase.TryGetGUIDAndLocalFileIdentifier(component, out string guid, out long id)
                        && id != 0 && !string.IsNullOrEmpty(guid))
                    {
                        control["sourceGuid"] = guid;
                        control["localFileId"] = id.ToString(CultureInfo.InvariantCulture);
                    }
                    else
                    {
                        control["sourceGuid"] = JsonValue.Null;
                        control["localFileId"] = JsonValue.Null;
                    }

                    var callbacks = JsonValue.NewArray();
                    if (component is Button button)
                    {
                        int count = button.onClick.GetPersistentEventCount();
                        for (int n = 0; n < Math.Min(count, MaxPersistentListeners); n++)
                        {
                            var target = button.onClick.GetPersistentTarget(n);
                            var callback = JsonValue.NewObject();
                            callback["targetType"] = target != null ? target.GetType().FullName : null;
                            callback["method"] = button.onClick.GetPersistentMethodName(n);
                            callbacks.Add(callback);
                        }
                        control["persistentCallbacksTruncated"] = count > MaxPersistentListeners;
                    }
                    control["persistentCallbacks"] = callbacks;
                    controls.Add(control);
                }
            }
            return controls;
        }

        private static JsonValue RelativePath(Transform root, Transform node)
        {
            var chain = new Stack<Transform>();
            for (Transform part = node; part != root; part = part.parent)
                chain.Push(part);
            var path = JsonValue.NewArray();
            foreach (Transform part in chain)
            {
                var segment = JsonValue.NewObject();
                segment["name"] = part.name;
                segment["siblingIndex"] = part.GetSiblingIndex();
                path.Add(segment);
            }
            return path;
        }
    }
}
