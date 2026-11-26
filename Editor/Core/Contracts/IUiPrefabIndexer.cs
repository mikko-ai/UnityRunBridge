using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Contracts
{
    public interface IIndexedClickBackend
    {
        Component[] GetActiveClickHandlers(GameObject target);
        bool MatchesClickHandlers(GameObject target, Component[] expected);
        InteractionOperationResult ClickIndexed(GameObject target, Component[] expected);
    }

    public interface IUiPrefabIndexer
    {
        JsonValue ReadControls(GameObject prefab);
    }
}
