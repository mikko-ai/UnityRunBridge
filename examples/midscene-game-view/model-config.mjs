import { readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";

export function modelConfigPath(home = homedir()) {
  return join(home, ".unity-agent-bridge", "plugins", "midscene.json");
}

const fields = ["baseUrl", "modelName", "modelFamily", "apiKeyEnv"];

export async function loadModelConfig({ home = homedir(), env = process.env } = {}) {
  const path = modelConfigPath(home);
  let raw;
  try {
    raw = await readFile(path, "utf8");
  } catch (error) {
    if (error.code !== "ENOENT") throw new Error(`无法读取 Midscene 配置：${path}`);
    // Keep existing environment-based SDK settings when the managed file is absent.
    if (env.MIDSCENE_MODEL_NAME?.trim()) return { source: "environment", path, modelConfig: undefined };
    throw new Error(`未配置 Midscene：请创建 ${path}，或设置 MIDSCENE_MODEL_NAME 等环境变量`);
  }
  let config;
  try {
    config = JSON.parse(raw);
  } catch {
    throw new Error(`Midscene 配置不是有效的 JSON：${path}`);
  }
  if (!config || typeof config !== "object" || Array.isArray(config) ||
      Object.keys(config).length !== fields.length ||
      !fields.every((key) => typeof config[key] === "string" && config[key].trim())) {
    throw new Error("Midscene 配置必须包含且仅包含 baseUrl、modelName、modelFamily、apiKeyEnv 四个非空字符串");
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
      MIDSCENE_MODEL_FAMILY: config.modelFamily.trim(),
      MIDSCENE_MODEL_API_KEY: apiKey,
    },
  };
}
