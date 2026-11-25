using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Contracts
{
    public interface IIndexedClickBackend
    {
        Component UniqueClickHandler(GameObject target);
        InteractionOperationResult ClickIndexed(Component expected);
    }

    public interface IUiPrefabIndexer
    {
        JsonValue ReadControls(GameObject prefab);
    }
}
