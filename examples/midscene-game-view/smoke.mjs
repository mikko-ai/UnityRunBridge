import { unityctlRunner } from "./game-view.mjs";
import { recordedAgent } from "./run-record.mjs";

const [project, target, expected] = process.argv.slice(2);
if (!project || !target || !expected) {
  console.error("Usage: npm run smoke -- <Unity project> <element description> <expected screen>");
  process.exitCode = 2;
} else {
  await recordedAgent(project, unityctlRunner(project), {
    name: "Midscene 视觉自测", mode: "model", reportName: "unity-visual-smoke",
  }, async (agent, record) => {
    await record.step("tap", "aiTap", () => agent.aiTap(target));
    await record.step("assert", "aiAssert", () => agent.aiAssert(expected));
  });
}
