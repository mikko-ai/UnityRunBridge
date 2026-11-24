import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
import { test } from "node:test";
import { UnityGameView } from "./game-view.mjs";

async function fixture(t) {
  const dir = await mkdtemp(join(tmpdir(), "unityrunbridge-midscene-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const path = join(dir, "frame.png");
  const bytes = Buffer.from("fixture frame");
  await writeFile(path, bytes);
  const snapshot = {
    path, width: 640, height: 360, coordinateSpace: "image-top-left", agentImageAccess: "allow",
    referenceScreen: { width: 1280, height: 720 },
  };
  return { snapshot, bytes };
}

test("reuses the size probe frame and sends the screenshot dimensions with the tap", async (t) => {
  const { snapshot, bytes } = await fixture(t);
  const calls = [];
  const device = new UnityGameView(async (args) => {
    calls.push(args);
    return snapshot;
  });

  assert.deepEqual(await device.size(), { width: 640, height: 360 });
  assert.equal(await device.screenshotBase64(), `data:image/png;base64,${bytes.toString("base64")}`);
  assert.equal(device.actionSpace()[0].name, "Tap");
  await device.tap({ x: 25.5, y: 40 });
  assert.deepEqual(calls, [
    ["snapshot"],
    ["click-at", "--x", "25.5", "--y", "40", "--image-width", "640", "--image-height", "360",
      "--reference-width", "1280", "--reference-height", "720"],
  ]);
  await assert.rejects(device.tap({ x: 25.5, y: 40 }), /Capture a screenshot/);
});

test("rejects resized or failed captures without retaining an actionable screenshot", async (t) => {
  const { snapshot } = await fixture(t);
  const device = new UnityGameView(async () => snapshot);
  await device.screenshotBase64();
  snapshot.referenceScreen = { width: 1920, height: 1080 };
  await assert.rejects(device.screenshotBase64(), /resolution changed/);
  await assert.rejects(device.tap({ x: 1, y: 2 }), /Capture a screenshot/);
});


test("rejects denied model access before attempting to read the PNG", async () => {
  const device = new UnityGameView(async () => ({
    path: "/missing.png", width: 640, height: 360, coordinateSpace: "image-top-left",
    referenceScreen: { width: 1280, height: 720 }, agentImageAccess: "deny",
  }));
  await assert.rejects(device.screenshotBase64(), /does not permit model access/);
});
