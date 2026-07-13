using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests
{
    public sealed class SessionControllerTests
    {
        [Test]
        public void IsAllowedSessionPath_AcceptsProjectUnityAgentSessionPath()
        {
            string projectPath = "/tmp/Game";
            string sessionPath = "/tmp/Game/.unity-agent/sessions/session-1";

            Assert.IsTrue(SessionController.IsAllowedSessionPath(projectPath, sessionPath));
        }

        [Test]
        public void IsAllowedSessionPath_RejectsPathOutsideProject()
        {
            string projectPath = "/tmp/Game";
            string sessionPath = "/tmp/Other/.unity-agent/sessions/session-1";

            Assert.IsFalse(SessionController.IsAllowedSessionPath(projectPath, sessionPath));
        }
    }
}
