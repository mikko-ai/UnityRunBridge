import { Agent } from "@midscene/core";
import { pathToFileURL } from "node:url";
import { unityctlRunner, UnityGameView } from "./game-view.mjs";

const falseAssertion = "midscene-fixture-negative";
const openButton = "点击画面中央的蓝色打开按钮";
const dialogPresent = "画面中央显示一个弹窗，弹窗里有上下排列的两个按钮";
const noDialog = "画面只有一个蓝色打开按钮，没有任何弹窗或上下排列的按钮";

export async function verifyModel(agent, readFocus) {
  if (await readFocus() !== "launcher") throw new Error("Fixture not ready: expected launcher focus");
  await agent.aiTap(openButton);
  // Independently verify that the model hit the intended control, not merely that aiTap returned.
  if (await readFocus() !== "confirm") throw new Error("The model did not open the expected dialog");
  await agent.aiAssert(dialogPresent);
  try {
    await agent.aiAssert(noDialog, falseAssertion);
  } catch (error) {
    // In the pinned SDK, transport/plan execution failures wrap their cause.
    // Do not use keepRawResponse: that option can map execution errors to pass:false.
    if (error instanceof Error && error.cause === undefined &&
        error.message.startsWith(`Assertion failed: ${falseAssertion}\nReason: `)) {
      return { tapVerified: true, positiveAssertion: "passed", negativeAssertion: "failed_as_expected" };
    }
    throw error;
  }
  throw new Error("The negative visual assertion incorrectly passed");
}

async function main() {
  const [project, executable, permission] = process.argv.slice(2);
  if (!project || !executable || permission !== "--allow-model-requests" || !process.env.MIDSCENE_MODEL_NAME) {
    console.error("需要测试工程、unityctl 路径、MIDSCENE_MODEL_NAME 和 --allow-model-requests");
    process.exitCode = 2;
    return;
  }
  const run = unityctlRunner(project, executable);
  const device = new UnityGameView(run);
  const agent = new Agent(device, { generateReport: true, reportFileName: "unity-2022-model-acceptance" });
  const focus = async () => (await run(["gameplay", "invoke", "UnityRunBridge.Examples.UiReviewDemo.FocusedControl"])).result;
  let result;
  try {
    result = await verifyModel(agent, focus);
  } finally {
    await agent.destroy();
    console.log(JSON.stringify({ ok: Boolean(result), ...result, reportPath: agent.reportFile }));
  }
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) await main();
