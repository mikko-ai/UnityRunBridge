import { appendFile, lstat, mkdir, realpath, rename, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { join, relative, resolve, sep } from "node:path";
import { UnityGameView } from "./game-view.mjs";

async function ensureDirectory(path) {
  await mkdir(path, { recursive: true, mode: 0o700 });
  const info = await lstat(path);
  if (!info.isDirectory() || info.isSymbolicLink()) throw new Error("Run directories must not be symlinks");
}

function inside(base, path) {
  const portion = relative(base, path);
  return portion !== "" && portion.split(sep)[0] !== ".." && !portion.startsWith(sep);
}

export class VisualRecord {
  #data;
  #active;
  #frameNumber = 0;

  static async create(project, name, mode) {
    const root = await realpath(project);
    for (const name of ["Assets", "Packages", "ProjectSettings"]) {
      if (!(await lstat(join(root, name))).isDirectory()) throw new Error("Expected a Unity project");
    }
    const agent = join(root, ".unity-agent");
    await ensureDirectory(agent);
    const parent = join(agent, "visual-runs");
    await ensureDirectory(parent);
    try { await writeFile(join(parent, ".gitignore"), "*\n", { flag: "wx", mode: 0o600 }); }
    catch (error) { if (error.code !== "EEXIST") throw error; }
    const id = randomUUID();
    const directory = join(parent, id);
    await mkdir(directory, { mode: 0o700 });
    const record = new VisualRecord(directory, {
      schemaVersion: 1, id, name, mode, status: "running", runnerPid: process.pid,
      startedAt: new Date().toISOString(), steps: [],
    });
    await record.#save();
    await record.#event("run-started");
    return record;
  }

  constructor(directory, data) {
    this.directory = directory;
    this.#data = data;
  }

  get key() { return `midscene:${this.#data.id}`; }

  async #save() {
    const pending = join(this.directory, ".record.pending");
    await writeFile(pending, JSON.stringify(this.#data, null, 2) + "\n", { mode: 0o600 });
    await rename(pending, join(this.directory, "run-record.json"));
  }

  async #event(type, fields = {}) {
    await appendFile(join(this.directory, "events.jsonl"),
      JSON.stringify({ type, at: new Date().toISOString(), ...fields }) + "\n", { mode: 0o600 });
  }

  async step(id, action, perform) {
    if (this.#active) throw new Error("VisualRecord requires serial steps");
    const step = { id, action, status: "running" };
    this.#active = step;
    this.#data.steps.push(step);
    await this.#save();
    await this.#event("step-started", { id, action });
    try {
      const result = await perform();
      step.status = result === "failed_as_expected" ? "failed_as_expected" : "passed";
      return result;
    } catch (error) {
      step.status = "failed";
      step.code = "visual_step_failed";
      throw error;
    } finally {
      this.#active = undefined;
      await this.#save();
      await this.#event("step-finished", { id, status: step.status, screenshot: step.screenshot });
    }
  }

  async frame(png) {
    if (!this.#active || !png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) return;
    const name = `frame-${++this.#frameNumber}.png`;
    await writeFile(join(this.directory, name), png, { mode: 0o600 });
    this.#active.screenshot = name;
    await this.#save();
  }

  async finish(status, reportFile) {
    if (typeof reportFile === "string") {
      const candidate = resolve(reportFile);
      try {
        if (inside(this.directory, candidate) && candidate.toLowerCase().endsWith(".html") &&
            await realpath(candidate) === candidate && (await lstat(candidate)).isFile()) {
          this.#data.report = relative(this.directory, candidate);
        }
      } catch {
        // Do not index an inaccessible or external report path.
      }
    }
    this.#data.status = status === "passed" && !this.#data.report ? "failed" : status;
    this.#data.endedAt = new Date().toISOString();
    await this.#save();
    await this.#event("run-finished", { status: this.#data.status });
    return this.#data.status;
  }
}

export async function recordedAgent(project, run, { name, mode, reportName }, execute) {
  const record = await VisualRecord.create(project, name, mode);
  const previousLocation = process.env.MIDSCENE_RUN_DIR;
  process.env.MIDSCENE_RUN_DIR = join(record.directory, "midscene_run");
  let agent;
  let status = "failed";
  let result;
  try {
    // Output location must be set before constructing the SDK report manager.
    const { Agent } = await import("@midscene/core");
    const device = new UnityGameView(run, { onFrame: (png) => record.frame(png) });
    agent = new Agent(device, { generateReport: true, reportFileName: reportName, autoPrintReportMsg: false });
    result = await execute(agent, record, device);
    await agent.destroy();
    status = "passed";
  } catch (error) {
    // Failed tasks still need the HTML evidence finalized; preserve the original error.
    try { if (agent && status !== "passed") await agent.destroy(); } catch { /* caller retains failure */ }
    throw error;
  } finally {
    if (previousLocation === undefined) delete process.env.MIDSCENE_RUN_DIR;
    else process.env.MIDSCENE_RUN_DIR = previousLocation;
    const finalStatus = await record.finish(status, agent?.reportFile);
    console.log(JSON.stringify({ ok: finalStatus === "passed", key: record.key, ...result }));
    if (status === "passed" && finalStatus !== "passed") throw new Error("Visual run did not produce an indexed report");
  }
  return result;
}
