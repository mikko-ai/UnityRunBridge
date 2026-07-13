using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests
{
    public sealed class BridgeErrorCodesTests
    {
        [Test]
        public void ResolveStatusCode_JsonValuePayload_UsesOkAndCodeFields()
        {
            JsonValue failure = JsonValue.NewObject();
            failure["ok"] = false;
            failure["code"] = "node_not_found";
            Assert.AreEqual(404, BridgeResponseStatus.ResolveStatusCode(failure));

            JsonValue success = JsonValue.NewObject();
            success["ok"] = true;
            success["code"] = "ignored_for_success";
            Assert.AreEqual(200, BridgeResponseStatus.ResolveStatusCode(success));
        }

        [Test]
        public void ResolveHttpStatus_KnownCodes()
        {
            Assert.AreEqual(401, BridgeErrorCodes.ResolveHttpStatus("unauthorized"));
            Assert.AreEqual(404, BridgeErrorCodes.ResolveHttpStatus("not_found"));
            Assert.AreEqual(404, BridgeErrorCodes.ResolveHttpStatus("job_not_found"));
            Assert.AreEqual(404, BridgeErrorCodes.ResolveHttpStatus("node_not_found"));
            Assert.AreEqual(409, BridgeErrorCodes.ResolveHttpStatus("busy"));
            Assert.AreEqual(409, BridgeErrorCodes.ResolveHttpStatus("compilation_failed"));
            Assert.AreEqual(409, BridgeErrorCodes.ResolveHttpStatus("not_in_play_mode"));
            Assert.AreEqual(422, BridgeErrorCodes.ResolveHttpStatus("invalid_request"));
            Assert.AreEqual(422, BridgeErrorCodes.ResolveHttpStatus("no_input_backend"));
            Assert.AreEqual(403, BridgeErrorCodes.ResolveHttpStatus("gameplay_disabled"));
            Assert.AreEqual(500, BridgeErrorCodes.ResolveHttpStatus("internal_error"));
            Assert.AreEqual(500, BridgeErrorCodes.ResolveHttpStatus("capture_failed"));
        }

        [Test]
        public void ResolveHttpStatus_UnmappedCode_DefaultsTo500()
        {
            Assert.AreEqual(500, BridgeErrorCodes.ResolveHttpStatus("something_totally_unregistered"));
        }

        [Test]
        public void ResolveHttpStatus_NullOrEmpty_DefaultsTo500()
        {
            Assert.AreEqual(500, BridgeErrorCodes.ResolveHttpStatus(null));
            Assert.AreEqual(500, BridgeErrorCodes.ResolveHttpStatus(string.Empty));
        }

        [Test]
        public void ResolveStatusCode_OkTrue_AlwaysReturns200RegardlessOfCode()
        {
            BridgeResponse response = BridgeResponse.Success("whatever_success_code", "ok");
            Assert.AreEqual(200, BridgeResponseStatus.ResolveStatusCode(response));
        }

        [Test]
        public void ResolveStatusCode_OkFalse_UsesErrorTable()
        {
            BridgeResponse response = BridgeResponse.Failure("not_found", "missing");
            Assert.AreEqual(404, BridgeResponseStatus.ResolveStatusCode(response));
        }

        [Test]
        public void ResolveStatusCode_NullPayload_Returns200()
        {
            Assert.AreEqual(200, BridgeResponseStatus.ResolveStatusCode(null));
        }
    }
}
