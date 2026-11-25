import { lstat, readFile, stat } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { parseTree, stripComments } from "jsonc-parser";

export function modelConfigPath(home = homedir(), legacy = false) {
  return join(home, ".unity-agent-bridge", "plugins", legacy ? "midscene.json" : "midscene.jsonc");
}

async function configExists(path) {
  try {
    await lstat(path);
    return true;
  } catch (error) {
    if (error.code === "ENOENT") return false;
    throw new Error(`无法检查 Midscene 配置路径：${path}`);
  }
}

const fields = ["baseUrl", "modelName", "modelFamily", "apiKeyEnv"];
const protocols = ["openai-chat", "openai-responses"];
// Keep in sync with the GPT adapters in the pinned Midscene SDK.
const responsesFamilies = ["gpt-5", "gpt-6"];

export async function loadModelConfig({ home = homedir(), env = process.env } = {}) {
  const jsonc = modelConfigPath(home);
  const json = modelConfigPath(home, true);
  const [hasJsonc, hasJson] = await Promise.all([configExists(jsonc), configExists(json)]);
  if (hasJsonc && hasJson) {
    throw new Error(`midscene.jsonc 与 midscene.json 同时存在，请在 ${join(home, ".unity-agent-bridge", "plugins")} 手动只保留其中一份`);
  }
  if (!hasJsonc && !hasJson) {
    if (env.MIDSCENE_MODEL_NAME?.trim()) return { source: "environment", path: jsonc, modelConfig: undefined };
    throw new Error(`未配置 Midscene：请创建 ${jsonc}，或设置 MIDSCENE_MODEL_NAME 等环境变量`);
  }
  const path = hasJsonc ? jsonc : json;
  let raw;
  try {
    if (!(await stat(path)).isFile()) throw new Error();
    raw = await readFile(path, "utf8");
  } catch {
    throw new Error(`无法读取 Midscene 配置：${path}`);
  }
  let config;
  try {
    if (hasJsonc) {
      const errors = [];
      // Reject recovered documents; use JSON.parse for the resulting plain data object.
      parseTree(raw, errors, { allowTrailingComma: false });
      if (errors.length) throw new Error();
    }
    config = JSON.parse(hasJsonc ? stripComments(raw, " ") : raw);
  } catch {
    throw new Error(`Midscene 配置不是有效的 ${hasJsonc ? "JSONC" : "JSON"}：${path}`);
  }
  if (!config || typeof config !== "object" || Array.isArray(config) ||
      Object.keys(config).some((key) => key !== "protocol" && !fields.includes(key)) ||
      !fields.every((key) => typeof config[key] === "string" && config[key].trim())) {
    throw new Error("Midscene 配置必须包含 baseUrl、modelName、modelFamily、apiKeyEnv 四个非空字符串，仅可额外填写 protocol");
  }
  const protocol = Object.hasOwn(config, "protocol") ? config.protocol : "openai-chat";
  if (!protocols.includes(protocol)) {
    throw new Error("Midscene 的 protocol 只接受 openai-chat（默认）或 openai-responses");
  }
  const modelFamily = config.modelFamily.trim();
  if (protocol === "openai-responses" && !responsesFamilies.includes(modelFamily)) {
    throw new Error("当前 Midscene SDK 的 openai-responses 仅支持 gpt-5 或 gpt-6 类型");
  }
  let url;
  try {
    url = new URL(config.baseUrl);
  } catch {
    throw new Error("Midscene 的 baseUrl 必须是 HTTP(S) API 地址");
  }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error("Midscene 的 baseUrl 必须是无凭据、查询参数和片段的 HTTP(S) API 地址");
  }
  if (/\/(?:chat\/completions|responses)\/*$/i.test(url.pathname)) {
    throw new Error("Midscene 的 baseUrl 应填 API 前缀（如 https://gateway.example/v1），不要附加 /chat/completions 或 /responses");
  }
  const keyName = config.apiKeyEnv;
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(keyName)) {
    throw new Error("Midscene 的 apiKeyEnv 必须是环境变量名，不能是密钥值");
  }
  const apiKey = Object.hasOwn(env, keyName) && env[keyName];
  if (typeof apiKey !== "string" || !apiKey.trim()) {
    throw new Error("Midscene 的 apiKeyEnv 指向的环境变量未设置或为空");
  }
  return {
    source: "unity-run-bridge",
    path,
    modelConfig: {
      MIDSCENE_MODEL_BASE_URL: config.baseUrl.trim(),
      MIDSCENE_MODEL_NAME: config.modelName.trim(),
      MIDSCENE_MODEL_FAMILY: modelFamily,
      MIDSCENE_MODEL_PROTOCOL: protocol,
      MIDSCENE_MODEL_API_KEY: apiKey,
    },
  };
}
