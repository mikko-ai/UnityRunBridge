// Unity 2022.3 smoke fixture. This run uses Midscene's report only; no AI methods are invoked.
import { unityctlRunner } from "./game-view.mjs";
import { recordedAgent } from "./run-record.mjs";

const [project, executable] = process.argv.slice(2);
if (!project || !executable) throw new Error("需要临时 Unity 工程和 unityctl 路径");
const run = unityctlRunner(project, executable);
const expected = new Error("intentional fixture assertion");
const focus = async () => (await run(["gameplay", "invoke", "UnityRunBridge.Examples.UiReviewDemo.FocusedControl"])).result;

try {
  await recordedAgent(project, run, {
    name: "UGUI 无模型运行记录", mode: "offline", reportName: "unity-offline-run-index",
  }, async (agent, record, device) => {
    await record.step("coordinate-tap", "click-at", async () => {
      if (await focus() !== "launcher") throw new Error("expected launcher focus");
      const screenshotBase64 = await device.screenshotBase64();
      await agent.recordToReport("点击前", { screenshotBase64 });
      const { width, height } = await device.size();
      await device.tap({ x: width / 2, y: height / 2 });
    });
    await record.step("failed-focus", "assert", async () => {
      const screenshotBase64 = await device.screenshotBase64();
      const actual = await focus();
      if (actual !== "confirm") throw new Error("fixture did not open the intended dialog");
      await agent.recordToReport("预期失败", { screenshotBase64, content: "弹窗已打开，焦点不是打开按钮。" });
      throw expected;
    });
  });
} catch (error) {
  if (error !== expected) throw error;
}
