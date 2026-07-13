using System.IO;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests
{
    public sealed class ArtifactPathGuardTests
    {
        [Test]
        public void IsAllowedSessionPath_AcceptsPathUnderSessions()
        {
            Assert.IsTrue(ArtifactPathGuard.IsAllowedSessionPath("/tmp/Game", "/tmp/Game/.unity-agent/sessions/session-1"));
        }

        [Test]
        public void IsAllowedSessionPath_RejectsPathOutsideProject()
        {
            Assert.IsFalse(ArtifactPathGuard.IsAllowedSessionPath("/tmp/Game", "/tmp/Other/.unity-agent/sessions/session-1"));
        }

        [Test]
        public void IsAllowedScratchPath_AcceptsPathUnderScratch()
        {
            Assert.IsTrue(ArtifactPathGuard.IsAllowedScratchPath("/tmp/Game", "/tmp/Game/.unity-agent/scratch/screenshot-1.png"));
        }

        [Test]
        public void IsAllowedScratchPath_RejectsSessionsPath()
        {
            Assert.IsFalse(ArtifactPathGuard.IsAllowedScratchPath("/tmp/Game", "/tmp/Game/.unity-agent/sessions/session-1"));
        }

        [Test]
        public void IsAllowedBuildsPath_AcceptsPathUnderBuilds()
        {
            Assert.IsTrue(ArtifactPathGuard.IsAllowedBuildsPath("/tmp/Game", "/tmp/Game/.unity-agent/builds/build-1.apk"));
        }

        [Test]
        public void IsAllowedArtifactPath_AcceptsSessionsOrScratch_RejectsOtherPaths()
        {
            Assert.IsTrue(ArtifactPathGuard.IsAllowedArtifactPath("/tmp/Game", "/tmp/Game/.unity-agent/sessions/session-1/artifacts/x.png"));
            Assert.IsTrue(ArtifactPathGuard.IsAllowedArtifactPath("/tmp/Game", "/tmp/Game/.unity-agent/scratch/x.png"));
            Assert.IsFalse(ArtifactPathGuard.IsAllowedArtifactPath("/tmp/Game", "/tmp/Game/.unity-agent/builds/x.apk"));
            Assert.IsFalse(ArtifactPathGuard.IsAllowedArtifactPath("/tmp/Game", "/tmp/Game/Assets/x.png"));
        }

        [Test]
        public void IsAllowed_RejectsNullOrEmptyInputs()
        {
            Assert.IsFalse(ArtifactPathGuard.IsAllowedArtifactPath(null, "/tmp/Game/.unity-agent/scratch/x.png"));
            Assert.IsFalse(ArtifactPathGuard.IsAllowedArtifactPath("/tmp/Game", null));
            Assert.IsFalse(ArtifactPathGuard.IsAllowedArtifactPath(string.Empty, string.Empty));
        }

        [Test]
        public void NextSequenceForDirectory_EmptyDirectory_ReturnsOne()
        {
            string directory = Path.Combine(Path.GetTempPath(), "ArtifactPathGuardTests_" + System.Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            try
            {
                int seq = ArtifactPathGuard.NextSequenceForDirectory(directory, "screenshot", ".png");
                Assert.AreEqual(1, seq);
            }
            finally
            {
                Directory.Delete(directory, recursive: true);
            }
        }

        [Test]
        public void NextSequenceForDirectory_WithExistingFiles_ReturnsMaxPlusOne()
        {
            string directory = Path.Combine(Path.GetTempPath(), "ArtifactPathGuardTests_" + System.Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            try
            {
                File.WriteAllText(Path.Combine(directory, "screenshot-1.png"), string.Empty);
                File.WriteAllText(Path.Combine(directory, "screenshot-3.png"), string.Empty);
                File.WriteAllText(Path.Combine(directory, "snapshot-9.json"), string.Empty);

                int seq = ArtifactPathGuard.NextSequenceForDirectory(directory, "screenshot", ".png");
                Assert.AreEqual(4, seq);
            }
            finally
            {
                Directory.Delete(directory, recursive: true);
            }
        }

        [Test]
        public void NextSequenceForDirectory_NonExistentDirectory_ReturnsOne()
        {
            string directory = Path.Combine(Path.GetTempPath(), "ArtifactPathGuardTests_does_not_exist_" + System.Guid.NewGuid().ToString("N"));
            Assert.AreEqual(1, ArtifactPathGuard.NextSequenceForDirectory(directory, "screenshot", ".png"));
        }

        [Test]
        public void ResolveArtifactDirectory_NoActiveSession_ReturnsScratchRoot()
        {
            SessionService.EndSession();

            string directory = ArtifactPathGuard.ResolveArtifactDirectory();

            string expected = ArtifactPathGuard.Normalize(ArtifactPathGuard.GetScratchRoot(ArtifactPathGuard.GetProjectRoot()));
            Assert.AreEqual(expected, ArtifactPathGuard.Normalize(directory));
            Assert.IsTrue(Directory.Exists(directory));
        }
    }
}
