import { Agent } from "@midscene/core";
import { unityctlRunner, UnityGameView } from "./game-view.mjs";

const [project, target, expected] = process.argv.slice(2);
if (!project || !target || !expected) {
  console.error("Usage: npm run smoke -- <Unity project> <element description> <expected screen>");
  process.exitCode = 2;
} else {
  const agent = new Agent(new UnityGameView(unityctlRunner(project)));
  try {
    await agent.aiTap(target);
    await agent.aiAssert(expected);
  } finally {
    await agent.destroy();
  }
}
