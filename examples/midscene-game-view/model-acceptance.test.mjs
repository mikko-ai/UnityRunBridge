import assert from "node:assert/strict";
import { test } from "node:test";
import { verifyModel } from "./model-acceptance.mjs";

function probe(runNegative) {
  const calls = [];
  const agent = {
    aiTap: async () => calls.push("tap"),
    aiAssert: async (prompt, label) => {
      calls.push(label === undefined ? "positive" : "negative");
      if (label) await runNegative(label);
    },
  };
  const focus = ["launcher", "confirm"];
  return { calls, result: verifyModel(agent, async () => focus.shift()) };
}

test("acceptance requires a genuine visual rejection after tap and positive assertion", async () => {
  const { calls, result } = probe(async (label) => {
    throw new Error(`Assertion failed: ${label}\nReason: the dialog is open`);
  });
  assert.deepEqual(await result, {
    tapVerified: true, positiveAssertion: "passed", negativeAssertion: "failed_as_expected",
  });
  assert.deepEqual(calls, ["tap", "positive", "negative"]);
});

test("acceptance does not mistake a service failure for the expected negative", async () => {
  const { result } = probe(async (label) => {
    throw new Error(`Assertion failed: ${label}\nReason: HTTP 503`, { cause: new Error("HTTP 503") });
  });
  await assert.rejects(result, /HTTP 503/);
});

test("acceptance refuses a false positive for the negative assertion", async () => {
  await assert.rejects(probe(async () => {}).result, /incorrectly passed/);
});
