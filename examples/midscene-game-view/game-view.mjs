import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { promisify } from "node:util";
import { AbstractInterface, defineActionTap } from "@midscene/core/device";

const execFileAsync = promisify(execFile);

function cliError(raw) {
  try {
    const { ok, code, message } = JSON.parse(raw);
    if (ok === false) return new Error([code, message].filter(Boolean).join(": "));
  } catch {
    // A process failure need not contain a JSON envelope.
  }
  return null;
}

export function unityctlRunner(project, executable = "unityctl") {
  const projectPath = resolve(project);
  return async (args) => {
    let stdout;
    try {
      ({ stdout } = await execFileAsync(executable, ["--project", projectPath, ...args], {
        timeout: 25_000,
      }));
    } catch (error) {
      throw cliError(error.stderr) ?? cliError(error.stdout) ?? new Error(
        `unityctl subprocess failed (${error.killed ? "timeout" : error.code ?? "unknown"}); not retried`,
      );
    }
    const result = JSON.parse(stdout);
    if (result.ok !== true) throw cliError(stdout) ?? new Error("Invalid unityctl response");
    return result;
  };
}

// Use one device per serial flow. This adapter does not own the Play Mode lifecycle.
export class UnityGameView extends AbstractInterface {
  interfaceType = "unity-game-view";
  #run;
  #frame;
  #pending;
  #onFrame;

  constructor(run, { onFrame } = {}) {
    super();
    this.#run = run;
    this.#onFrame = onFrame;
  }

  async #capture() {
    const snapshot = await this.#run(["snapshot"]);
    const { width, height, referenceScreen, path } = snapshot;
    if (snapshot.coordinateSpace !== "image-top-left" || typeof path !== "string" ||
        ![width, height, referenceScreen?.width, referenceScreen?.height].every(
          (dimension) => Number.isSafeInteger(dimension) && dimension > 0,
        )) {
      throw new Error("Screenshot metadata missing; upgrade both unityctl and the Editor Bridge");
    }

    if (snapshot.agentImageAccess !== "allow") {
      throw new Error("Project does not permit model access to Game View screenshots");
    }

    const previous = this.#frame;
    if (previous && (width !== previous.width || height !== previous.height ||
        referenceScreen.width !== previous.referenceScreen.width ||
        referenceScreen.height !== previous.referenceScreen.height)) {
      throw new Error("Game View resolution changed; start a new visual flow");
    }

    const png = await readFile(path);
    if (this.#onFrame) await this.#onFrame(png);
    return { width, height, referenceScreen, base64: `data:image/png;base64,${png.toString("base64")}` };
  }

  async screenshotBase64() {
    const pending = this.#pending;
    this.#pending = undefined;
    // Invalidate the actionable frame before capturing. A failed capture must not leave it clickable.
    const previous = this.#frame;
    try {
      this.#frame = pending ?? await this.#capture();
      return this.#frame.base64;
    } catch (error) {
      this.#frame = previous && { ...previous, base64: undefined };
      throw error;
    }
  }

  async size() {
    const { width, height } = this.#frame ?? (this.#pending ??= await this.#capture());
    return { width, height };
  }

  async tap({ x, y }) {
    const frame = this.#frame;
    if (!frame?.base64) throw new Error("Capture a screenshot before tapping");
    this.#frame = { ...frame, base64: undefined };
    await this.#run([
      "click-at", "--x", String(x), "--y", String(y),
      "--image-width", String(frame.width), "--image-height", String(frame.height),
      "--reference-width", String(frame.referenceScreen.width),
      "--reference-height", String(frame.referenceScreen.height),
    ]);
  }

  actionSpace() {
    return [defineActionTap((point) => this.tap(point))];
  }
}
