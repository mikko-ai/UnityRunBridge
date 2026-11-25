const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const test = require("node:test");
const {createContext, runInContext} = require("node:vm");

const source = readFileSync(join(__dirname, "../unityctl/watch_assets/watch.js"), "utf8");
const origin = Date.parse("2026-11-25T12:00:00Z");
const at = (seconds) => new Date(origin + seconds * 1000).toISOString();

function monitor() {
  const node = () => ({
    textContent: "", dataset: {}, children: [],
    addEventListener() {}, removeAttribute() {}, toggleAttribute() {},
    append(...children) { this.children.push(...children); },
    replaceChildren() { this.children = []; },
  });
  const byId = new Map();
  const document = {
    createElement: node,
    getElementById(id) {
      if (!byId.has(id)) byId.set(id, node());
      return byId.get(id);
    },
  };
  let seconds = 0;
  class TestDate extends Date {
    static now() { return origin + seconds * 1000; }
  }
  const context = createContext({
    document, Date: TestDate, AbortSignal: {timeout() {}}, fetch: () => new Promise(() => {}),
  });
  runInContext(source, context);
  return {
    render(events, now, status = "running", sessionId = "demo") {
      seconds = now;
      context.state = {events, status, sessionId, editor: {online: false}};
      runInContext("receive(state)", context);
      return {
        total: byId.get("run-time").hidden ? null : byId.get("run-time").textContent,
        status: byId.get("run-status").textContent,
        step: byId.get("steps").children[0]?.children.find((child) => child.className === "step-time muted"),
      };
    },
  };
}

test("active steps tick, Agent gaps are distinct and final time freezes", () => {
  const {render} = monitor();
  const events = [{type: "run-started", kind: "agent", at: "2026-11-25T12:00:00.000001+00:00"}];
  assert.equal(render(events, 3).status, "等待 Agent 下一步");
  events.push({type: "step-started", stepIndex: 0, status: "running", at: at(18)});
  const active = render(events, 18.4);
  assert.equal(active.status, "运行中 · 第 1 步");
  assert.equal(active.total, "已运行 00:18");
  assert.equal(active.step.textContent, "+00:18 · 已执行 0.4 秒");
  assert.equal(render(events, 19).step.textContent, "+00:18 · 已执行 1.0 秒");
  events.push({type: "step-finished", stepIndex: 0, status: "passed", at: at(19)});
  assert.equal(render(events, 21).status, "等待 Agent 下一步");
  assert.equal(render(events, 21).step.textContent, "+00:18 · 耗时 1.0 秒");
  events.push({type: "run-finished", status: "passed", at: at(23)});
  assert.equal(render(events, 90, "passed").total, "总耗时 00:23");
  assert.equal(render(events, 110, "passed").total, "总耗时 00:23");
});

test("interrupted or untimed records do not invent an end time or leak another session's time", () => {
  const {render} = monitor();
  const events = [
    {type: "run-started", kind: "agent", at: at(0)},
    {type: "step-started", stepIndex: 0, status: "running", at: at(4)},
  ];
  const interrupted = render(events, 90, "interrupted");
  assert.equal(interrupted.total, "已记录耗时 00:04");
  assert.equal(interrupted.step.textContent, "+00:04");
  assert.equal(render([{type: "run-started", at: "invalid"}], 92, "running", "other").total, null);
  assert.equal(render([], 92, "waiting", null).total, null);
});
