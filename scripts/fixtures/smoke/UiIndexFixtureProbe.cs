using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

public sealed class UiIndexFixtureProbe : MonoBehaviour
{
    public Transform prefabRoot;
    public Button expected;
    public Button other;
    public Button dynamic;
    public GameObject cover;

    private GameObject clone;
    private int clicks;
    private int wrongClicks;
    private int extraClicks;
    private bool mutateOnEnter;
    private bool coverOnDown;

    private void Awake()
    {
        Application.runInBackground = true;
        LogIdentity("PLAY", prefabRoot.gameObject);
        LogIdentity("PLAY-COMPONENT", expected);
        expected.onClick.AddListener(() => clicks++);
        other.onClick.AddListener(() => wrongClicks++);
        dynamic.onClick.AddListener(() => clicks++);
    }

    #if UNITY_EDITOR
    public static void LogIdentity(string phase, Object target)
    {
        const string path = "Assets/Menu/Panel.prefab";
        var g = UnityEditor.GlobalObjectId.GetGlobalObjectIdSlow(target);
        UnityEditor.AssetDatabase.TryGetGUIDAndLocalFileIdentifier(target, out string guid, out long fileId);
        var plain = UnityEditor.PrefabUtility.GetCorrespondingObjectFromSource(target);
        var at = UnityEditor.PrefabUtility.GetCorrespondingObjectFromSourceAtPath(target, path);
        var restored = UnityEditor.GlobalObjectId.GlobalObjectIdentifierToObjectSlow(g);
        Debug.Log($"UIIDXPROBE {phase} global={g} asset={guid}:{fileId} source={plain} at={at} roundTrip={restored == target}");
    }
    #endif

    public static string Control(string action)
    {
        var fixture = FindObjectOfType<UiIndexFixtureProbe>();
        switch (action)
        {
            case "counts":
                return fixture.clicks + ":" + fixture.wrongClicks;
            case "extra-count":
                return fixture.extraClicks.ToString();
            case "clone":
                fixture.clone = Instantiate(fixture.prefabRoot.gameObject, fixture.prefabRoot.parent);
                fixture.clone.name = fixture.prefabRoot.name;
                break;
            case "replace-root":
                fixture.clone = Instantiate(fixture.prefabRoot.gameObject, fixture.prefabRoot.parent);
                fixture.prefabRoot.name = "RetiredPanel";
                fixture.prefabRoot.gameObject.SetActive(false);
                fixture.clone.name = "Panel";
                break;
            case "restore-root":
                fixture.clone.name = "RetiredClone";
                fixture.clone.SetActive(false);
                Destroy(fixture.clone);
                fixture.prefabRoot.name = "Panel";
                fixture.prefabRoot.gameObject.SetActive(true);
                break;
            case "switch-scene":
                UnityEditor.SceneManagement.EditorSceneManager.LoadSceneInPlayMode("Assets/Scenes/Other.unity",
                    new UnityEngine.SceneManagement.LoadSceneParameters(UnityEngine.SceneManagement.LoadSceneMode.Single));
                break;
            case "no-source":
                fixture.clone = Instantiate(fixture.prefabRoot.gameObject, fixture.prefabRoot.parent);
                fixture.clone.name = "RuntimeClone";
                LogIdentity("CLONE", fixture.clone);
                break;
            case "remove-clone":
                if (fixture.clone != null)
                {
                    fixture.clone.name = "Retired";
                    fixture.clone.SetActive(false);
                    Destroy(fixture.clone);
                }
                break;
            case "rename":
                fixture.expected.name = "Renamed";
                break;
            case "reorder":
                fixture.expected.transform.SetSiblingIndex(1);
                break;
            case "restore":
                fixture.expected.name = "Action";
                fixture.expected.transform.SetSiblingIndex(0);
                fixture.expected.interactable = true;
                fixture.expected.gameObject.SetActive(true);
                fixture.cover.SetActive(false);
                break;
            case "cover":
                fixture.cover.SetActive(true);
                break;
            case "disabled":
                fixture.expected.interactable = false;
                break;
            case "inactive":
                fixture.expected.gameObject.SetActive(false);
                break;
            case "rename-dynamic":
                fixture.dynamic.name = "DynamicChanged";
                break;
            case "persist-canvas":
                DontDestroyOnLoad(fixture.dynamic.transform.root.gameObject);
                break;
            case "restore-canvas":
                UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(
                    fixture.dynamic.transform.root.gameObject, fixture.gameObject.scene);
                break;
            case "multiple-handlers":
                fixture.AddExtraHandler(fixture.dynamic);
                break;
            case "multiple-prefab-handlers":
                fixture.AddExtraHandler(fixture.expected);
                break;
            case "mutate-on-enter":
                fixture.mutateOnEnter = true;
                break;
            case "replace-extra-handler":
                DestroyImmediate(fixture.dynamic.GetComponent<EventTrigger>());
                fixture.AddExtraHandler(fixture.dynamic);
                break;
            case "cover-on-down":
                fixture.mutateOnEnter = false;
                fixture.dynamic.GetComponent<EventTrigger>().enabled = true;
                fixture.cover.GetComponent<RectTransform>().anchoredPosition =
                    fixture.dynamic.GetComponent<RectTransform>().anchoredPosition;
                var coverTrigger = fixture.cover.AddComponent<EventTrigger>();
                var coverClick = new EventTrigger.Entry { eventID = EventTriggerType.PointerClick };
                coverClick.callback.AddListener(_ => fixture.wrongClicks++);
                coverTrigger.triggers.Add(coverClick);
                fixture.coverOnDown = true;
                break;
            case "clear-down-cover":
                fixture.coverOnDown = false;
                fixture.cover.SetActive(false);
                break;
            default: throw new System.ArgumentException("Unknown fixture action");
        }
        return "ok";
    }

    private void AddExtraHandler(Button button)
    {
        var trigger = button.gameObject.AddComponent<EventTrigger>();
        var click = new EventTrigger.Entry { eventID = EventTriggerType.PointerClick };
        click.callback.AddListener(_ => extraClicks++);
        trigger.triggers.Add(click);
        var enter = new EventTrigger.Entry { eventID = EventTriggerType.PointerEnter };
        enter.callback.AddListener(_ =>
        {
            if (mutateOnEnter)
                trigger.enabled = false;
        });
        trigger.triggers.Add(enter);
        var down = new EventTrigger.Entry { eventID = EventTriggerType.PointerDown };
        down.callback.AddListener(_ =>
        {
            if (coverOnDown)
            {
                cover.SetActive(true);
                Canvas.ForceUpdateCanvases();
            }
        });
        trigger.triggers.Add(down);
    }
}
