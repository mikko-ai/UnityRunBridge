using System.IO;
using NUnit.Framework;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Tests
{
    public sealed class SessionLogWriterTests
    {
        private string tempDirectory;

        [SetUp]
        public void SetUp()
        {
            tempDirectory = Path.Combine(Path.GetTempPath(), "unity-agent-bridge-tests-" + Path.GetRandomFileName());
        }

        [TearDown]
        public void TearDown()
        {
            if (Directory.Exists(tempDirectory))
            {
                Directory.Delete(tempDirectory, recursive: true);
            }
        }

        [Test]
        public void Write_IncludesSequenceAndRunIndex()
        {
            string logPath = Path.Combine(tempDirectory, "unity-console.jsonl");
            using (SessionLogWriter writer = new SessionLogWriter(logPath))
            {
                writer.Write("hello", string.Empty, LogType.Log, 7, 2);
            }

            string line = File.ReadAllLines(logPath)[0];
            StringAssert.Contains("\"sequence\":7", line);
            StringAssert.Contains("\"runIndex\":2", line);
            StringAssert.Contains("\"type\":\"Log\"", line);
            StringAssert.Contains("\"message\":\"hello\"", line);
        }

        [Test]
        public void WriteEvent_WritesBridgeEventBoundaryEntry()
        {
            string logPath = Path.Combine(tempDirectory, "unity-console.jsonl");
            using (SessionLogWriter writer = new SessionLogWriter(logPath))
            {
                writer.WriteEvent("runStarted", 3, 1);
                writer.WriteEvent("runEnded", 4, 1);
            }

            string[] lines = File.ReadAllLines(logPath);
            StringAssert.Contains("\"type\":\"BridgeEvent\"", lines[0]);
            StringAssert.Contains("\"event\":\"runStarted\"", lines[0]);
            StringAssert.Contains("\"sequence\":3", lines[0]);
            StringAssert.Contains("\"runIndex\":1", lines[0]);
            StringAssert.Contains("\"event\":\"runEnded\"", lines[1]);
            StringAssert.Contains("\"sequence\":4", lines[1]);
        }

        [Test]
        public void WriteEvent_SharesSequenceChainWithLogs()
        {
            string logPath = Path.Combine(tempDirectory, "unity-console.jsonl");
            using (SessionLogWriter writer = new SessionLogWriter(logPath))
            {
                writer.WriteEvent("runStarted", 1, 1);
                writer.Write("Awake", string.Empty, LogType.Log, 2, 1);
                writer.WriteEvent("runEnded", 3, 1);
            }

            string[] lines = File.ReadAllLines(logPath);
            Assert.AreEqual(3, lines.Length);
            StringAssert.Contains("\"sequence\":1", lines[0]);
            StringAssert.Contains("\"sequence\":2", lines[1]);
            StringAssert.Contains("\"sequence\":3", lines[2]);
        }
    }
}
