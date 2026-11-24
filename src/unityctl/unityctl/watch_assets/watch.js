"use strict";

const get = (id) => document.getElementById(id);
const labels = {
  running: "运行中", passed: "已通过", failed: "失败", skipped: "已跳过",
  interrupted: "已中断", unverified: "未断言", waiting: "等待任务", unknown: "状态未知",
};
const editorState = {
  idle: "空闲", compiling: "编译中", updating: "更新中", enteringPlay: "进入 Play Mode",
  playing: "Play Mode", exitingPlay: "退出 Play Mode", paused: "已暂停",
};
const actionNames = {
  "open-scene": "打开场景", play: "进入 Play Mode", stop: "退出 Play Mode",
  "wait-for": "等待条件", assert: "断言", click: "点击", screenshot: "截图",
  snapshot: "截图", "click-at": "按画面点击", gameplay: "读取 Unity 探针", input: "输入", "set-value": "设置控件值", invoke: "调用探针",
};
let currentSession = null;
let chosenStep = null;
let stepRows = [];
let visibleFrame = "";
let eventCount = -1;
const rows = new Map();

function writeText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function pickFrame() {
  if (chosenStep !== null) return stepRows.find((step) => step.stepIndex === chosenStep && step.frame);
  return stepRows.filter((step) => step.frame).at(-1);
}

function renderFrame() {
  const step = pickFrame();
  const url = step ? `frame/${encodeURIComponent(currentSession)}/${encodeURIComponent(step.frame)}` : "";
  get("placeholder").hidden = Boolean(step);
  get("projection").hidden = !step;
  get("follow").hidden = chosenStep === null;
  if (url !== visibleFrame) {
    visibleFrame = url;
    if (url) get("frame").src = url;
    else get("frame").removeAttribute("src");
  }
  const point = step?.marker;
  const valid = point && get("frame").complete && get("frame").naturalWidth > 0 && [point.x, point.y].every((value) => Number.isFinite(value) && value >= 0 && value <= 1);
  const marker = get("marker");
  marker.toggleAttribute("hidden", !valid);
  if (valid) {
    const translation = `translate(${point.x * 1000} ${point.y * 1000})`;
    for (const child of marker.children) child.setAttribute("transform", translation);
  }
  writeText(get("frame-caption"), step
    ? `${chosenStep === null ? "最新" : "回看"} · 步骤 ${step.stepIndex + 1} · ${step.id}${valid ? " · 已标记点击落点" : ""}`
    : "按步骤更新，不是视频直播。");
}

function updateRows() {
  const list = get("steps");
  const followScroll = list.scrollHeight - list.clientHeight - list.scrollTop < 36;
  for (const step of stepRows) {
    if (!rows.has(step.stepIndex)) {
      const li = document.createElement("li");
      const index = document.createElement("span");
      index.className = "muted";
      index.textContent = String(step.stepIndex + 1).padStart(2, "0");
      const caption = document.createElement("span");
      caption.className = "step-id";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "step-id";
      button.addEventListener("click", () => {
        chosenStep = step.stepIndex;
        renderFrame();
      });
      const status = document.createElement("span");
      const details = document.createElement("details");
      details.className = "step-detail";
      details.open = true;
      const summary = document.createElement("summary");
      summary.textContent = "操作详情";
      const why = document.createElement("p");
      const command = document.createElement("code");
      const result = document.createElement("p");
      details.append(summary, why, command, result);
      li.append(index, caption, button, status, details);
      list.append(li);
      rows.set(step.stepIndex, {caption, button, status, details, why, command, result});
    }
    const {caption, button, status, details, why, command, result} = rows.get(step.stepIndex);
    const label = `${actionNames[step.action] || step.action} · ${step.id}${step.code ? ` · ${step.code}` : ""}`;
    writeText(caption, label);
    writeText(button, label);
    caption.hidden = Boolean(step.frame);
    button.hidden = !step.frame;
    writeText(status, labels[step.status] || "状态未知");
    status.dataset.status = step.status;
    details.hidden = !step.why;
    if (step.why) {
      writeText(why, `目的：${step.why}`);
      writeText(command, step.command || "");
      const v = step.verification;
      const actual = v && (v.found ? JSON.stringify(v.actual) ?? "非标量" : "未返回");
      writeText(result, v
        ? `验证：${v.field}，预期 ${JSON.stringify(v.expected)}，实际 ${actual}（${v.passed ? "通过" : "失败"}）`
        : step.clicked ? `实际命中：${step.clicked}` : step.code ? `命令结果：${step.code}` : "等待命令返回");
    }
  }
  if (chosenStep === null && followScroll) list.scrollTop = list.scrollHeight;
  get("timeline-empty").hidden = stepRows.length > 0;
}

function receive(state) {
  writeText(get("editor"), state.editor.online ? `Bridge 在线 · ${editorState[state.editor.state] || "状态未知"}` : "Bridge 离线");
  const newSession = currentSession !== state.sessionId;
  if (newSession) {
    currentSession = state.sessionId;
    chosenStep = null;
    eventCount = -1;
    rows.clear();
    get("steps").replaceChildren();
  }
  if (eventCount !== state.events.length) {
    eventCount = state.events.length;
    const byStep = new Map();
    for (const event of state.events) {
      if (!Number.isInteger(event.stepIndex)) continue;
      byStep.set(event.stepIndex, {...byStep.get(event.stepIndex), ...event});
    }
    stepRows = [...byStep.values()];
    const start = state.events.find((event) => event.type === "run-started");
    writeText(get("run-name"), start?.name || "尚无监看会话");
    writeText(get("step-count"), start ? Number.isInteger(start.stepsTotal) ? `${stepRows.length} / ${start.stepsTotal}` : `${stepRows.length} 步` : "");
    updateRows();
    renderFrame();
  }
  const running = stepRows.find((step) => step.status === "running");
  const status = get("run-status");
  status.dataset.status = state.status;
  writeText(status, running && state.status === "running"
    ? `运行中 · 第 ${running.stepIndex + 1} 步` : labels[state.status] || "状态未知");
}

get("frame").addEventListener("load", renderFrame);

get("follow").addEventListener("click", () => {
  chosenStep = null;
  renderFrame();
  get("screen-title").focus();
});

async function poll() {
  try {
    const response = await fetch("state", {cache: "no-store", signal: AbortSignal.timeout(4000)});
    if (!response.ok) throw new Error("read failed");
    receive(await response.json());
  } catch {
    const status = get("run-status");
    status.dataset.status = "interrupted";
    writeText(status, "监看连接暂不可用 · 正在重试");
  } finally {
    setTimeout(poll, 450);
  }
}

poll();
