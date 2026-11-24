import { pathToFileURL } from "node:url";
import { unityctlRunner } from "./game-view.mjs";
import { recordedAgent } from "./run-record.mjs";

const falseAssertion = "midscene-fixture-negative";
const openButton = "点击画面中央的蓝色打开按钮";
const dialogPresent = "画面中央显示一个弹窗，弹窗里有上下排列的两个按钮";
const noDialog = "画面只有一个蓝色打开按钮，没有任何弹窗或上下排列的按钮";

export async function verifyModel(agent, readFocus, step = (_id, _action, perform) => perform()) {
  if (await readFocus() !== "launcher") throw new Error("Fixture not ready: expected launcher focus");
  await step("tap", "aiTap", async () => {
    await agent.aiTap(openButton);
    // Verify the hit independently of the model and its reported success.
    if (await readFocus() !== "confirm") throw new Error("The model did not open the expected dialog");
  });
  await step("positive", "aiAssert", () => agent.aiAssert(dialogPresent));
  const negativeAssertion = await step("negative", "aiAssert", async () => {
    try {
      await agent.aiAssert(noDialog, falseAssertion);
    } catch (error) {
      // In the pinned SDK service failures wrap their cause. keepRawResponse would erase the distinction.
      if (error instanceof Error && error.cause === undefined &&
          error.message.startsWith(`Assertion failed: ${falseAssertion}\nReason: `)) {
        return "failed_as_expected";
      }
      throw error;
    }
    throw new Error("The negative visual assertion incorrectly passed");
  });
  return { tapVerified: true, positiveAssertion: "passed", negativeAssertion };
}

async function main() {
  const [project, executable, permission] = process.argv.slice(2);
  if (!project || !executable || permission !== "--allow-model-requests" || !process.env.MIDSCENE_MODEL_NAME) {
    console.error("需要测试工程、unityctl 路径、MIDSCENE_MODEL_NAME 和 --allow-model-requests");
    process.exitCode = 2;
    return;
  }
  const run = unityctlRunner(project, executable);
  const focus = async () => (await run(["gameplay", "invoke", "UnityRunBridge.Examples.UiReviewDemo.FocusedControl"])).result;
  await recordedAgent(project, run, {
    name: "Midscene 模型验收", mode: "model", reportName: "unity-2022-model-acceptance",
  }, (agent, record) => verifyModel(agent, focus, record.step.bind(record)));
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) await main();
