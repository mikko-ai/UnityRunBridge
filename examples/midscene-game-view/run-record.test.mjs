import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { VisualRecord } from "./run-record.mjs";

async function projectFor(t) {
  const project = await mkdtemp(join(tmpdir(), "unityctl-record-"));
  t.after(() => rm(project, { recursive: true, force: true }));
  await Promise.all(["Assets", "Packages", "ProjectSettings"].map((name) => mkdir(join(project, name))));
  return project;
}

test("record preserves the failing step and scoped screenshot and HTML", async (t) => {
  const project = await projectFor(t);
  const run = await VisualRecord.create(project, "UGUI", "offline");
  const png = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  await assert.rejects(run.step("focus", "assert", async () => {
    await run.frame(png);
    throw new Error("fail");
  }), /fail/);
  const report = join(run.directory, "report.html");
  await writeFile(report, "test");
  await run.finish("failed", report);
  const data = JSON.parse(await readFile(join(run.directory, "run-record.json"), "utf8"));
  assert.equal(data.report, "report.html");
  assert.equal(data.status, "failed");
  assert.deepEqual(data.steps, [{ id: "focus", action: "assert", status: "failed",
    screenshot: "frame-1.png", code: "visual_step_failed" }]);
});

test("a report outside the run cannot count as a successful visual run", async (t) => {
  const project = await projectFor(t);
  const run = await VisualRecord.create(project, "UGUI", "offline");
  const report = join(project, "external.html");
  await writeFile(report, "outside");
  assert.equal(await run.finish("passed", report), "failed");
  const data = JSON.parse(await readFile(join(run.directory, "run-record.json"), "utf8"));
  assert.equal(data.report, undefined);
});
