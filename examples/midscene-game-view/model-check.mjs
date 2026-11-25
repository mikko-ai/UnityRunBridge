import { loadModelConfig } from "./model-config.mjs";

try {
  const { source, path, modelConfig } = await loadModelConfig();
  const protocol = modelConfig?.MIDSCENE_MODEL_PROTOCOL;
  console.log(JSON.stringify({ ok: true, source, path, protocol, connectionTested: false }));
} catch (error) {
  console.error(error.message);
  process.exitCode = 2;
}
