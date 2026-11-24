# Unity 2022.3 回归验收

在 Unity **2022.3.62f2** 上执行。脚本为每次运行创建独立的测试项目，不修改现有游戏工程，也不读取模型配置。

```bash
# UTF：EditMode 通过、PlayMode 通过、预期断言失败（须返回失败及堆栈）
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py utf --unity /path/to/Unity.app

# Game View：1280×720 / 720×1280 抓帧、缩放坐标点击、错误尺寸拒绝和遮挡
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py visual --unity /path/to/Unity.app

# 监看：步骤、点击标记和失败现场
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py watch --unity /path/to/Unity.app

# 依次执行 UTF、横竖屏和监看；也可从 UNITY_BIN 读取编辑器路径
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py all
```

`visual` 需要可交互的桌面会话：会启动临时 Editor，并切换到 Game View。不要在无图形或只允许后台服务的 Runner 上把它标成通过。每次结果保留在 `.tmp/unity-smoke/run-*/`，可用 `--output` 指定父目录。临时目录及其 Unity Library 由调用方按需清理。

普通 GitHub CI 只在 GitHub 托管 Runner 上运行 Python、无模型 Midscene 适配器和 UPM 包校验，不启动 Unity。UTF、Game View、实时监看和统一运行记录的实机回归请在本机执行；分发包验收可使用下方的 `delivery`。Release 发布流程及其验收门禁不变。

## 单独验收 Midscene 真实模型

仅在你确认模型配置及画面传输范围后运行；不在 `all` 或默认 CI 中调用模型。先在 `examples/midscene-game-view/` 运行 `npm ci --ignore-scripts`，再按 [Midscene 模型配置说明](https://www.midscenejs.com/model-api-setup) 给本机进程配置环境变量（不要把密钥写入仓库或日志）。

```bash
uv run --project src/unityctl --locked --no-dev python scripts/run-unity-smoke.py model \
  --unity /path/to/Unity.app --allow-model-requests
```

该命令只启动临时 UGUI 演示。验收会确认模型点击了真实按钮、正确认出弹窗，并拒绝一条与画面相反的断言。模型网络/执行出错不能算负例通过。结束后在输出目录中查看 `model-acceptance.log`，或在临时项目里用 `unityctl runs list --kind midscene` 和 `runs show` 找到报告；不要把报告未经审查上传。

四类运行记录汇总的回归见 [统一运行记录](unityctl-runs.md)。

## 从分发包验收

此套件用干净的临时工程验收本地分发，不依赖 GitHub Release，不替换本机正在用的 `unityctl`：

```bash
(cd examples/midscene-game-view && npm ci --ignore-scripts)
mkdir -p .tmp
out="$(mktemp -d "$PWD/.tmp/delivery.XXXXXX")"
uv build --wheel src/unityctl --out-dir "$out"
uv venv "$out/venv"
uv pip install --python "$out/venv/bin/python" "$out"/*.whl
archive="$(DIST_DIR="$out/upm" bash scripts/package-upm.sh | tail -1)"
"$out/venv/bin/python" scripts/run-unity-smoke.py delivery \
  --unity /path/to/Unity.app --upm "$archive" --output "$out/runtime"
```

套件会检查 `init --yes` 不擅自写入包依赖、显式安装本地 UPM、重复初始化不覆盖配置、内置 Skill 可安装，以及 Editor 未启动、非 Play Mode 和 Gameplay 未授权时的诊断。Unity 必须实际从 tarball 加载 Bridge，并跑完 Scenario 监看正负例以及 Agent、Scenario、UTF、Midscene 四类运行记录。Agent 回归用的是合成场景已知按钮坐标，验证事件、落点及断言证据，不作为视觉模型验收。自动准备演示场景时由脚本启动 Editor；随后核对 `unityctl start` 不重复启动现有实例。全程不调用视觉模型。
