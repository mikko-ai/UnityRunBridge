using System;
using System.Collections.Generic;
using System.IO;
using Mk.UnityAgentBridge.Editor.Interaction;
using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace Mk.UnityAgentBridge.Editor.Tests.Interaction
{
    public sealed class InteractionAuditLogTests
    {
        [SetUp]
        public void SetUp()
        {
            InteractionAuditLog.ResetForTests();
        }

        [TearDown]
        public void TearDown()
        {
            InteractionAuditLog.ResetForTests();
        }

        [Test]
        public void BuildRequestSummary_Input_RedactsTextAndUsesUtf16Length()
        {
            JsonValue body = JsonParser.Parse(
                "{\"path\":\"Main/Login\",\"text\":\"secret😀\",\"submit\":true}");

            JsonValue request = InteractionAuditLog.BuildRequestSummary("input", body);

            Assert.AreEqual("Main/Login", request["path"].AsString);
            Assert.AreEqual("secret😀".Length, request["textLength"].AsInt);
            Assert.IsTrue(request["submit"].AsBoolean);
            Assert.IsFalse(request.ContainsKey("text"));
            StringAssert.DoesNotContain("secret", request.ToString());
        }

        [Test]
        public void BuildRequestSummary_Click_DefaultsForceToFalse()
        {
            JsonValue request = InteractionAuditLog.BuildRequestSummary(
                "click", JsonParser.Parse("{\"path\":\"Main/Button\"}"));

            Assert.AreEqual("Main/Button", request["path"].AsString);
            Assert.IsFalse(request["force"].AsBoolean);
        }

        [TestCase("12.5")]
        [TestCase("true")]
        public void BuildRequestSummary_SetValue_PreservesNumberAndBooleanValues(string rawValue)
        {
            JsonValue request = InteractionAuditLog.BuildRequestSummary(
                "set-value", JsonParser.Parse("{\"path\":\"Main/Slider\",\"value\":" + rawValue + "}"));

            Assert.AreEqual(rawValue, request["value"].ToString());
            Assert.AreEqual(rawValue == "true" ? "boolean" : "number", request["valueKind"].AsString);
        }

        [Test]
        public void BuildRequestSummary_SetValue_PreservesOnlyNumericXYObject()
        {
            JsonValue request = InteractionAuditLog.BuildRequestSummary(
                "set-value", JsonParser.Parse("{\"value\":{\"x\":1,\"y\":2}}"));

            Assert.AreEqual("object", request["valueKind"].AsString);
            Assert.AreEqual(2, request["value"].Count);
            Assert.AreEqual(1, request["value"]["x"].AsInt);
            Assert.AreEqual(2, request["value"]["y"].AsInt);
        }

        [TestCase("\"secret😀\"", "string")]
        [TestCase("[1,2]", "unknown")]
        [TestCase("null", "unknown")]
        [TestCase("{\"x\":1,\"y\":2,\"z\":3}", "unknown")]
        public void BuildRequestSummary_SetValue_RedactsUnsafeValues(string rawValue, string expectedKind)
        {
            JsonValue request = InteractionAuditLog.BuildRequestSummary(
                "set-value", JsonParser.Parse("{\"value\":" + rawValue + "}"));

            Assert.AreEqual(expectedKind, request["valueKind"].AsString);
            Assert.IsFalse(request.ContainsKey("value"));
            if (expectedKind == "string")
            {
                Assert.AreEqual("secret😀".Length, request["valueLength"].AsInt);
            }
        }

        [Test]
        public void BuildRequestSummary_SetValue_MissingValue_IsInvalid()
        {
            JsonValue request = InteractionAuditLog.BuildRequestSummary(
                "set-value", JsonParser.Parse("{\"path\":\"Main/Slider\"}"));

            Assert.AreEqual("invalid", request["valueKind"].AsString);
            Assert.IsFalse(request.ContainsKey("value"));
        }

        [Test]
        public void AppendFromResponse_ClickSuccess_WritesWhitelistedResponseFields()
        {
            List<string> lines = CaptureLines();
            JsonValue response = JsonParser.Parse(
                "{\"ok\":true,\"clicked\":\"Main/Button\",\"raycastHit\":null," +
                "\"events\":[\"pointerDown\",\"pointerClick\"],\"forced\":false,\"ignored\":\"no\"}");

            InteractionAuditLog.AppendFromResponse(
                "click",
                InteractionAuditLog.BuildRequestSummary("click", JsonParser.Parse("{\"path\":\"Main/Button\"}")),
                "Assets/Scenes/Main.unity",
                response,
                -3);

            JsonValue line = ParseSingleLine(lines);
            AssertCommonLine(line, "click", true, "ok");
            Assert.AreEqual("Assets/Scenes/Main.unity", line["scene"].AsString);
            Assert.AreEqual("Main/Button", line["clicked"].AsString);
            Assert.IsTrue(line["raycastHit"].IsNull);
            Assert.AreEqual("pointerDown", line["events"][0].AsString);
            Assert.IsFalse(line["forced"].AsBoolean);
            Assert.IsFalse(line.ContainsKey("ignored"));
            Assert.AreEqual(0, line["durationMs"].AsLong);
        }

        [Test]
        public void AppendFromResponse_Occluded_WritesMessageAndBlockedBy()
        {
            List<string> lines = CaptureLines();
            JsonValue response = JsonParser.Parse(
                "{\"ok\":false,\"code\":\"occluded\",\"message\":\"blocked\",\"blockedBy\":\"Main/Overlay\"}");

            InteractionAuditLog.AppendFromResponse(
                "click",
                InteractionAuditLog.BuildRequestSummary("click", JsonParser.Parse("{\"path\":\"Main/Button\"}")),
                null,
                response,
                3);

            JsonValue line = ParseSingleLine(lines);
            AssertCommonLine(line, "click", false, "occluded");
            Assert.AreEqual("blocked", line["message"].AsString);
            Assert.AreEqual("Main/Overlay", line["blockedBy"].AsString);
            Assert.IsFalse(line.ContainsKey("scene"));
        }

        [Test]
        public void AppendFromResponse_SetValueSuccess_CopiesTopLevelComponent()
        {
            List<string> lines = CaptureLines();
            JsonValue response = JsonParser.Parse("{\"ok\":true,\"component\":\"UnityEngine.UI.Slider\"}");

            InteractionAuditLog.AppendFromResponse(
                "set-value",
                InteractionAuditLog.BuildRequestSummary("set-value", JsonParser.Parse("{\"path\":\"Main/Slider\",\"value\":1}")),
                null,
                response,
                3);

            JsonValue line = ParseSingleLine(lines);
            AssertCommonLine(line, "set-value", true, "ok");
            Assert.AreEqual("UnityEngine.UI.Slider", line["component"].AsString);
        }

        [Test]
        public void AppendFromResponse_WhenAppenderThrows_LogsWarningAndDoesNotThrow()
        {
            InteractionAuditLog.SetHooksForTests(
                () => "/virtual/artifacts",
                (_, __) => throw new IOException("disk full"));
            JsonValue request = InteractionAuditLog.BuildRequestSummary(
                "click", JsonParser.Parse("{\"path\":\"Main/Button\"}"));

            LogAssert.Expect(
                LogType.Warning,
                "Unity Agent Bridge: 写入 interaction-actions.jsonl 失败：disk full");

            Assert.DoesNotThrow(() => InteractionAuditLog.AppendFromResponse(
                "click", request, null, BridgeResponse.Success("ok", "unused"), 3));
        }

        [Test]
        public void AppendFromResponse_WithoutSession_AppendsParseableLineToScratch()
        {
            SessionService.EndSession();
            string path = Path.Combine(
                ArtifactPathGuard.GetScratchRoot(ArtifactPathGuard.GetProjectRoot()),
                "interaction-actions.jsonl");
            bool existed = File.Exists(path);
            byte[] original = existed ? File.ReadAllBytes(path) : null;

            try
            {
                int previousLineCount = CountLines(path);
                InteractionAuditLog.AppendFromResponse(
                    "input",
                    InteractionAuditLog.BuildRequestSummary("input", JsonParser.Parse("{\"path\":\"Main/Input\",\"text\":\"secret\"}")),
                    null,
                    BridgeResponse.Success("ok", "input applied"),
                    2);

                Assert.AreEqual(previousLineCount + 1, CountLines(path));
                JsonParser.Parse(LastLine(path));
            }
            finally
            {
                RestoreFile(path, existed, original);
            }
        }

        [Test]
        public void AppendFromResponse_WithSession_AppendsParseableLineToSessionArtifacts()
        {
            string projectRoot = ArtifactPathGuard.GetProjectRoot();
            string sessionPath = Path.Combine(
                ArtifactPathGuard.GetSessionsRoot(projectRoot),
                "interaction-audit-test-" + Guid.NewGuid().ToString("N"));
            string path = Path.Combine(sessionPath, "artifacts", "interaction-actions.jsonl");

            try
            {
                Assert.IsTrue(SessionService.StartSession("interaction-audit-test", sessionPath).ok);
                InteractionAuditLog.AppendFromResponse(
                    "click",
                    InteractionAuditLog.BuildRequestSummary("click", JsonParser.Parse("{\"path\":\"Main/Button\"}")),
                    null,
                    JsonParser.Parse("{\"ok\":true,\"clicked\":\"Main/Button\",\"raycastHit\":null,\"events\":[],\"forced\":false}"),
                    2);

                Assert.IsTrue(File.Exists(path));
                JsonParser.Parse(LastLine(path));
            }
            finally
            {
                SessionService.EndSession();
                if (Directory.Exists(sessionPath))
                {
                    Directory.Delete(sessionPath, true);
                }
            }
        }

        private static List<string> CaptureLines()
        {
            List<string> lines = new List<string>();
            InteractionAuditLog.SetHooksForTests(
                () => "/virtual/artifacts",
                (path, text) =>
                {
                    Assert.AreEqual(
                        Path.Combine("/virtual/artifacts", "interaction-actions.jsonl"),
                        path);
                    lines.Add(text);
                });
            return lines;
        }

        private static JsonValue ParseSingleLine(List<string> lines)
        {
            Assert.AreEqual(1, lines.Count);
            StringAssert.EndsWith("\n", lines[0]);
            return JsonParser.Parse(lines[0]);
        }

        private static void AssertCommonLine(JsonValue line, string action, bool ok, string code)
        {
            Assert.IsTrue(line.ContainsKey("time"));
            Assert.AreEqual(action, line["action"].AsString);
            Assert.AreEqual(ok, line["ok"].AsBoolean);
            Assert.AreEqual(code, line["code"].AsString);
            Assert.IsTrue(line["request"].IsObject);
            Assert.GreaterOrEqual(line["durationMs"].AsLong, 0);
            Assert.AreEqual(-1, line["playModeFrame"].AsInt);
            Assert.IsTrue(line["activeScenePath"].IsString);
        }

        private static int CountLines(string path)
        {
            return File.Exists(path) ? File.ReadAllLines(path).Length : 0;
        }

        private static string LastLine(string path)
        {
            string[] lines = File.ReadAllLines(path);
            return lines[lines.Length - 1];
        }

        private static void RestoreFile(string path, bool existed, byte[] original)
        {
            if (existed)
            {
                File.WriteAllBytes(path, original);
            }
            else if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
    }
}
