using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests
{
    public sealed class SceneControllerTests
    {
        [Test]
        public void IsValidProjectScenePath_AcceptsAssetsScene()
        {
            Assert.IsTrue(SceneController.IsValidProjectScenePath("Assets/Scenes/Login.unity"));
        }

        [Test]
        public void IsValidProjectScenePath_RejectsAbsolutePath()
        {
            Assert.IsFalse(SceneController.IsValidProjectScenePath("/game/Login.unity"));
        }

        [Test]
        public void IsValidProjectScenePath_RejectsNonSceneAsset()
        {
            Assert.IsFalse(SceneController.IsValidProjectScenePath("Assets/Scenes/Login.prefab"));
        }
    }
}
