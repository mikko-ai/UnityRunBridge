import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { loadModelConfig, modelConfigPath } from "./model-config.mjs";

const fixture = {
  baseUrl: "https://provider.example/v1",
  modelName: "vision-model",
  modelFamily: "qwen3-vl",
  apiKeyEnv: "VISION_API_KEY",
};

async function setup(t) {
  const home = await mkdtemp(join(tmpdir(), "unity-midscene-home-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const file = modelConfigPath(home);
  await mkdir(dirname(file), { recursive: true });
  return { home, file };
}

test("uses the UnityRunBridge home with explicit configuration ahead of legacy environment", async (t) => {
  const { home, file } = await setup(t);
  assert.equal(file, join(home, ".unity-agent-bridge/plugins/midscene.json"));
  await writeFile(file, JSON.stringify(fixture));
  const env = { VISION_API_KEY: "dummy-key", MIDSCENE_MODEL_NAME: "legacy" };
  const config = await loadModelConfig({ home, env });
  assert.deepEqual(config, {
    source: "unity-run-bridge", path: file, modelConfig: {
      MIDSCENE_MODEL_BASE_URL: fixture.baseUrl,
      MIDSCENE_MODEL_NAME: fixture.modelName,
      MIDSCENE_MODEL_FAMILY: fixture.modelFamily,
      MIDSCENE_MODEL_API_KEY: "dummy-key",
    },
  });
  assert.deepEqual(env, { VISION_API_KEY: "dummy-key", MIDSCENE_MODEL_NAME: "legacy" });
});

test("preserves legacy environment configuration only when no managed file exists", async (t) => {
  const { home, file } = await setup(t);
  await assert.rejects(loadModelConfig({ home, env: {} }), /未配置 Midscene/);
  const env = { MIDSCENE_MODEL_NAME: "legacy" };
  assert.deepEqual(await loadModelConfig({ home, env }), {
    source: "environment", path: file, modelConfig: undefined,
  });
  await writeFile(file, "{ bad");
  await assert.rejects(loadModelConfig({ home, env }), /不是有效的 JSON/);
});

test("rejects embedded credentials and a missing referenced key without exposing values", async (t) => {
  const { home, file } = await setup(t);
  await writeFile(file, JSON.stringify({ ...fixture, baseUrl: "https://user:private@provider.example/v1" }));
  await assert.rejects(loadModelConfig({ home, env: {} }), (error) =>
    error.message.includes("无凭据") && !error.message.includes("private"));
  await writeFile(file, JSON.stringify({ ...fixture, apiKey: "private" }));
  await assert.rejects(loadModelConfig({ home, env: {} }), (error) =>
    error.message.includes("仅包含") && !error.message.includes("private"));
  await writeFile(file, JSON.stringify(fixture));
  await assert.rejects(loadModelConfig({ home, env: { MIDSCENE_MODEL_NAME: "legacy" } }), /环境变量未设置/);
});

test("the configuration check never prints the key or claims to connect", async (t) => {
  const { home, file } = await setup(t);
  await writeFile(file, JSON.stringify(fixture));
  const result = spawnSync(process.execPath, [fileURLToPath(new URL("./model-check.mjs", import.meta.url))], {
    env: { HOME: home, USERPROFILE: home, VISION_API_KEY: "never-print-this-key" }, encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), {
    ok: true, source: "unity-run-bridge", path: file, connectionTested: false,
  });
});
