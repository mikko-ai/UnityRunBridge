import { loadModelConfig } from "./model-config.mjs";

try {
  const { source, path } = await loadModelConfig();
  console.log(JSON.stringify({ ok: true, source, path, connectionTested: false }));
} catch (error) {
  console.error(error.message);
  process.exitCode = 2;
}
