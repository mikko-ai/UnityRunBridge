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

test("reads an existing strict JSON file ahead of legacy environment variables", async (t) => {
  const { home } = await setup(t);
  const file = modelConfigPath(home, true);
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
      MIDSCENE_MODEL_PROTOCOL: "openai-chat",
    },
  });
  assert.deepEqual(env, { VISION_API_KEY: "dummy-key", MIDSCENE_MODEL_NAME: "legacy" });
});

test("loads comments in JSONC but preserves comment-like characters inside strings", async (t) => {
  const { home, file } = await setup(t);
  assert.equal(file, join(home, ".unity-agent-bridge/plugins/midscene.jsonc"));
  const modelName = 'vision/*literal*/-"//text"';
  await writeFile(file, '// User configuration\n' +
    JSON.stringify({ ...fixture, modelName }, null, 2)
      .replace('"apiKeyEnv"', '/* env name, not the key */ "apiKeyEnv"'));
  const { modelConfig, path } = await loadModelConfig({ home, env: { VISION_API_KEY: "dummy-key" } });
  assert.equal(path, file);
  assert.equal(modelConfig.MIDSCENE_MODEL_BASE_URL, fixture.baseUrl);
  assert.equal(modelConfig.MIDSCENE_MODEL_NAME, modelName);
});

test("rejects dual files before parsing or falling back to environment", async (t) => {
  const { home, file } = await setup(t);
  await writeFile(file, 'unreadable config');
  await writeFile(modelConfigPath(home, true), JSON.stringify(fixture));
  await assert.rejects(loadModelConfig({ home, env: { MIDSCENE_MODEL_NAME: "legacy" } }),
    /midscene.jsonc 与 midscene.json 同时存在.*只保留其中一份/);
});

test("rejects malformed JSONC and does not accept comments in legacy JSON", async (t) => {
  const { home, file } = await setup(t);
  await writeFile(file, JSON.stringify(fixture) + " /* never closed");
  await assert.rejects(loadModelConfig({ home, env: {} }), /不是有效的 JSONC/);
  await rm(file);
  await writeFile(modelConfigPath(home, true), "// not strict JSON\n" + JSON.stringify(fixture));
  await assert.rejects(loadModelConfig({ home, env: {} }), /不是有效的 JSON：/);
});

test("preserves legacy environment configuration only when no managed file exists", async (t) => {
  const { home, file } = await setup(t);
  await assert.rejects(loadModelConfig({ home, env: {} }), /未配置 Midscene/);
  const env = { MIDSCENE_MODEL_NAME: "legacy" };
  assert.deepEqual(await loadModelConfig({ home, env }), {
    source: "environment", path: file, modelConfig: undefined,
  });
  await writeFile(file, "{ bad");
  await assert.rejects(loadModelConfig({ home, env }), /不是有效的 JSONC/);
});

test("rejects embedded credentials and a missing referenced key without exposing values", async (t) => {
  const { home, file } = await setup(t);
  await writeFile(file, JSON.stringify({ ...fixture, baseUrl: "https://user:private@provider.example/v1" }));
  await assert.rejects(loadModelConfig({ home, env: {} }), (error) =>
    error.message.includes("无凭据") && !error.message.includes("private"));
  await writeFile(file, JSON.stringify({ ...fixture, apiKey: "private" }));
  await assert.rejects(loadModelConfig({ home, env: {} }), (error) =>
    error.message.includes("仅可额外填写 protocol") && !error.message.includes("private"));
  await writeFile(file, JSON.stringify(fixture));
  await assert.rejects(loadModelConfig({ home, env: { MIDSCENE_MODEL_NAME: "legacy" } }), /环境变量未设置/);
});

test("validates the two protocol spellings and the pinned SDK's Responses model families", async (t) => {
  const { home, file } = await setup(t);
  const env = { VISION_API_KEY: "dummy-key" };
  for (const protocol of ["responses", "OpenAI-Responses", "", null, 1]) {
    await writeFile(file, JSON.stringify({ ...fixture, protocol }));
    await assert.rejects(loadModelConfig({ home, env }), /openai-chat（默认）或 openai-responses/);
  }
  await writeFile(file, JSON.stringify({ ...fixture, protocol: "openai-responses" }));
  await assert.rejects(loadModelConfig({ home, env }), /仅支持 gpt-5 或 gpt-6/);

  for (const modelFamily of ["gpt-5", "gpt-6"]) {
    await writeFile(file, JSON.stringify({ ...fixture, modelFamily, protocol: "openai-responses" }));
    assert.equal((await loadModelConfig({ home, env })).modelConfig.MIDSCENE_MODEL_PROTOCOL, "openai-responses");
  }
});

test("accepts provider prefixes but rejects complete API operation URLs", async (t) => {
  const { home, file } = await setup(t);
  const env = { VISION_API_KEY: "dummy-key" };
  for (const path of ["/v1/chat/completions", "/v1/responses/"]) {
    await writeFile(file, JSON.stringify({ ...fixture, baseUrl: "https://provider.example" + path }));
    await assert.rejects(loadModelConfig({ home, env }), /应填 API 前缀/);
  }
  await writeFile(file, JSON.stringify({ ...fixture, baseUrl: "https://provider.example/api/v3", protocol: "openai-chat" }));
  assert.equal((await loadModelConfig({ home, env })).modelConfig.MIDSCENE_MODEL_BASE_URL, "https://provider.example/api/v3");
});

test("the configuration check never prints the key or claims to connect", async (t) => {
  const { home, file } = await setup(t);
  await writeFile(file, JSON.stringify(fixture));
  const result = spawnSync(process.execPath, [fileURLToPath(new URL("./model-check.mjs", import.meta.url))], {
    env: { HOME: home, USERPROFILE: home, VISION_API_KEY: "never-print-this-key" }, encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), {
    ok: true, source: "unity-run-bridge", path: file, protocol: "openai-chat", connectionTested: false,
  });
});
