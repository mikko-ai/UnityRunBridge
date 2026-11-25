using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Contracts
{
    public interface IUiPrefabIndexer
    {
        JsonValue ReadControls(GameObject prefab);
    }
}
