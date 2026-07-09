# UnityRunBridge

UnityRunBridge 提供一个轻量级的 Editor-only Unity 包和一个 Python CLI，用于通过脚本或 Agent 控制本地 Unity Editor 实例。

当前功能范围：

- 启动 Unity Editor 进程。
- 通过本地 HTTP 桥接查询 Editor 状态（含编译状态、Play Mode 状态）。
- 进入、停止、暂停和恢复 Play Mode，命令会等待 Unity 真正收敛到目标状态才返回。
- 打开 Unity 项目中的场景。
- 触发脚本重编译并等待结果（`unityctl refresh`）。
- 诊断本机环境与 Bridge 连通性（`unityctl doctor`）。
- 只读查询 UGUI Hierarchy 结构（`unityctl hierarchy`）与 Play Mode 截图（`unityctl snapshot`）。
- 模拟 UGUI 点击 / 输入 / 设值（`click` / `input` / `set-value`），带射线遮挡验证。
- 零侵入调用游戏侧暴露的命令（`unityctl gameplay`，默认关闭）。
- 录制 UGUI 语义动作为 `actions.jsonl`（`unityctl record`），供复盘或生成 scenario 草稿。
- 用 JSON 文件固化「操作 → 断言」的自动化验证脚本并可重复执行（`unityctl scenario`）。
- `ProfilerRecorder` 逐帧性能采样，用于改动前后的相对回归比较（`unityctl profile`）。
- 独立进程执行 Player 构建并生成结构化报告（`unityctl build`）。
- 项目健康检查：编译、缺失脚本引用、构建场景列表、包一致性（`unityctl health`）。

Bridge 在 Unity Editor 内监听 `127.0.0.1` 上的某个端口（默认从 `17890` 开始，被占用会自动顺延），实际端口和鉴权 token 由 Unity 写入项目内的 `.unity-agent/bridge.json` 握手文件，CLI 会自动读取，不需要手动配置。

## 环境要求

- Unity Editor `2022.3` 或更高版本。
- Python `3.11` 或更高版本。
- `uv` 用于 Python 依赖管理和命令执行。

## 添加 Unity 包

将包添加到 Unity 项目的 `Packages/manifest.json` 中。推荐直接使用 `unityctl init`：它会检测 manifest 是否已包含 bridge 包依赖，缺失时询问是否写入（详见下文「初始化 Unity Project」）。也可以按以下方式手动添加。

### 正式引用（推荐）

通过 GitHub 远端地址引用已发布的 UPM 包：

```json
{
  "dependencies": {
    "com.mk.unity-agent-bridge": "https://github.com/mikko-ai/UnityRunBridge.git#upm/vX.Y.Z"
  }
}
```

将 `upm/vX.Y.Z` 替换为需要的版本 tag（例如 `upm/v0.1.0`）。该包仅在 Editor 下运行，并在 Unity Editor 加载时启动本地桥接服务。

### 本地开发

在本仓库内开发包时，可使用 `file:` 引用：

```json
{
  "dependencies": {
    "com.mk.unity-agent-bridge": "file:/absolute/path/to/UnityRunBridge/packages/com.mk.unity-agent-bridge"
  }
}
```

请使用本仓库在你机器上的绝对路径。

## 安装 CLI

### 从 GitHub Release 安装（正式）

在 [GitHub Releases](https://github.com/mikko-ai/UnityRunBridge/releases) 页面找到对应版本，使用 wheel 安装：

```bash
uv tool install --force https://github.com/mikko-ai/UnityRunBridge/releases/download/vX.Y.Z/unity_run_bridge-X.Y.Z-py3-none-any.whl
```

将 `vX.Y.Z` 和 wheel 文件名替换为实际版本。安装后验证：

```bash
unityctl --version
```

### 本地开发安装

本地开发安装：

```bash
cd /absolute/path/to/UnityRunBridge
uv tool install --editable ./src/unityctl
```

安装后可以在任意目录运行：

```bash
unityctl --help
```

开发调试 CLI 时，也可以继续在 `src/unityctl` 下使用低层开发命令：

```bash
cd src/unityctl
uv run unityctl --help
```

## 命令参考

所有命令以 JSON 输出。全局选项 `--project PATH` 可指定 Unity 项目根目录（默认从当前目录向上查找）。

| 命令 | 说明 |
| --- | --- |
| `init` | 初始化 `.unity-agent` 配置目录 |
| `config show` | 输出合并后的有效配置 |
| `config validate` | 校验 `config.json` 与 `config.local.json` |
| `config set-local KEY VALUE` | 更新本机配置字段 |
| `start` | 启动 Unity Editor（默认等待 Bridge 握手） |
| `status` | 查询 Editor 状态（编译、Play Mode、当前场景等） |
| `play` | 进入 Play Mode（可选 `--session` 记录运行日志） |
| `stop` | 退出 Play Mode（可选 `--latest` 生成 summary） |
| `pause` / `resume` | 暂停 / 恢复 Play Mode |
| `open-scene PATH` | 在 Editor 中打开场景 |
| `refresh` | 触发脚本重编译并等待完成 |
| `logs` / `errors` / `summary` | 读取 session 日志、错误与 summary |
| `doctor` | 诊断项目配置与 Bridge 连通性 |
| `hierarchy roots/tree/find/ancestors/inspect` | 只读查询 UGUI Hierarchy 结构 |
| `snapshot` | Play Mode 截图（落盘 PNG） |
| `click` / `input` / `set-value` | 模拟 UGUI 点击 / 输入 / 设值（需 Play Mode） |
| `gameplay list` / `gameplay invoke` | 零侵入调用游戏侧暴露的命令（默认关闭） |
| `record start` / `record status` / `record stop` | 录制 UGUI 语义动作到 `actions.jsonl` |
| `profile start` / `profile status` / `profile stop` | `ProfilerRecorder` 逐帧性能采样 |
| `scenario validate` / `scenario run` / `scenario from-recording` | 可复跑的自动化验证脚本引擎 |
| `build` | 独立进程执行 Player 构建并生成 `build-report.json` |
| `health` | 项目健康检查（编译/缺失脚本/构建场景/包一致性） |
| `skills init` / `skills update` | 安装 / 更新内置 agent skills（unityctl 参考手册 + project skill creator） |

查看完整参数说明：

```bash
unityctl --help
unityctl play --help
unityctl config --help
```

## 初始化 Unity Project

在 Unity 项目根目录执行。Unity 项目根目录指包含 `Assets`、`Packages` 和 `ProjectSettings` 的目录：

```bash
cd /absolute/path/to/UnityProject
unityctl init
```

`init` 会展示检测到的 Unity project root，并要求确认后才写入文件。脚本或 CI 中可以使用 `unityctl init --yes`。

`unityctl init` 会创建：

```text
.unity-agent/config.json
.unity-agent/config.local.json
.unity-agent/schemas/*.json
```

如果已经初始化，`init` 只补缺失文件，不会覆盖已有的 `config.json` / `config.local.json`（内置 schema 文件除外，它们总是被刷新）。`config.json` 保存可提交的项目配置，例如 Unity 版本、Bridge 期望端口和超时时间。`config.local.json` 保存本机配置，例如 Unity 可执行文件路径，应被 `.gitignore` 忽略。

`init` 还会检测 `Packages/manifest.json` 是否已包含 `com.mk.unity-agent-bridge` 依赖：

- 已存在：保持不动，输出 `"packageAction": "already_installed"`。
- 缺失且在交互终端中：询问是否写入，同意后写入依赖（默认引用与 CLI 版本一致的 `upm/vX.Y.Z` tag）。
- 缺失且非交互（含 `--yes`）：默认不修改 manifest，仅在 `nextSteps` 中提示。

相关参数：

```bash
unityctl init --install-package                 # 缺失时直接写入，不询问（适合脚本/CI，可与 --yes 组合）
unityctl init --no-install-package              # 跳过 manifest 检测与写入
unityctl init --install-package --package-ref "file:/absolute/path/to/pkg.tgz"  # 自定义依赖引用
```

配置文件是纯 JSON，不支持注释；字段说明见 `.unity-agent/schemas/config.schema.json` 和 `config.local.schema.json`。

校验配置：

```bash
unityctl config validate
```

查看有效配置：

```bash
unityctl config show
```

更新本机 Unity 路径：

```bash
unityctl config set-local unityExecutablePath "/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
```

## 启动 Unity

```bash
unityctl start
```

默认会等待 Unity Editor 完成握手（写出 `bridge.json` 并可被连接）。若项目已在运行且 Bridge 可达，重复执行会直接返回 `already_running`，不会重复启动 Unity 进程。需要只启动 Unity 进程时：

```bash
unityctl start --no-wait
```

启动成功后，Unity 日志中会出现类似：

```text
Unity Agent Bridge listening on http://127.0.0.1:17890/
```

## 控制 Editor

在 Unity 项目根目录或其子目录执行：

```bash
unityctl status
unityctl play
unityctl pause
unityctl resume
unityctl stop
unityctl open-scene "Assets/Scenes/Login.unity"
unityctl refresh
unityctl doctor
```

所有命令均输出 JSON。成功响应中包含 `"ok": true`。`play`/`stop`/`refresh` 会轮询 Unity 状态直到收敛（进入/退出 Play Mode、编译完成），可以用 `--timeout` 覆盖配置中的默认超时，用 `--no-wait`（`refresh` 除外）跳过等待。

## Session-based 运行观测

运行带 session 的 Play Mode：

```bash
unityctl play \
  --session login-flow \
  --scene Assets/Scenes/Login.unity \
  --task "verify login flow"
```

CLI 会在 Unity 项目下创建：

```text
<ProjectRoot>/.unity-agent/sessions/<sessionId>/
  session.json
  unity-console.jsonl
```

停止并生成 `summary.json`：

```bash
unityctl stop --latest
```

如果收敛过程中出现编译失败、超时或 Unity Editor 意外退出，`session.json` 的 `status` 会被标记为 `failed` 并记录 `failedReason`，同时仍然会生成对应的 `summary.json`。

查看日志和 summary：

```bash
unityctl logs --latest --limit 100
unityctl errors --latest
unityctl summary --latest
```

日志量大时，`logs` 支持在查询侧过滤（完整日志始终保留在 `unity-console.jsonl` 中）：

```bash
unityctl logs --latest --grep "关键字"             # 按 message 子串过滤（不区分大小写）
unityctl logs --latest --type Error,Exception     # 按日志类型过滤
unityctl logs --latest --after-sequence 500       # 只看 sequence > 500 的增量日志
```

`logs` 与 `errors` 输出的每条日志都带 `line` 字段（该条日志在 `unity-console.jsonl` 中的 1-based 行号），需要查看某条日志前后的上下文时，可以据此直接定位到完整日志文件。

也可以显式指定 session 目录：

```bash
unityctl summary --session-path "/absolute/path/to/UnityProject/.unity-agent/sessions/2026-07-02_100000_login-flow"
```

可选 log rules（保存到 Unity 项目的 `.unity-agent/log-rules.json`）：

```json
{
  "ignore": [
    {
      "type": "Error",
      "messageContains": "Expected test error"
    }
  ],
  "watch": [
    {
      "messageContains": "本次要验证的关键日志片段"
    }
  ]
}
```

两类规则的匹配字段都是 `type` 和 `messageContains`（同时给出时须同时满足）：

- `ignore`（降噪）：命中的 Error/Exception/Assert 日志不再计入问题统计。`errors` 命令与 `summary` 命令共用同一套分类逻辑，口径保持一致。
- `watch`（聚焦）：命中的日志在生成 summary 时被提取进 `watchedLogs` 字段（带 `line` 行号，最多保留最近 50 条，`watchedCount` 记录全量命中数），不影响问题分类。适合在 `play` 前声明本次运行的关注点，`stop --latest` 后直接从 summary 拿到命中日志。

## 查询 Hierarchy / 截图（只读，Play Mode 内外均可用于查询）

```bash
unityctl hierarchy roots                                # 列出所有已加载场景的根节点
unityctl hierarchy tree MainCanvas --depth 2            # 从指定节点向下遍历子树
unityctl hierarchy find --component Button --active-only
unityctl hierarchy inspect MainCanvas/ShopWindow/BuyButton
unityctl snapshot --reason assert_failure                # 需 Play Mode，截图落盘为 PNG
```

节点用 `path`（`/` 分隔）或 `instanceId` 定位；`snapshot` 受 `config.json` 里 `capture.screenshot` 配置管控（开关、配额、是否允许 agent 主动请求）。

## 模拟 UI 操作 / Gameplay 命令桥（需 Play Mode）

```bash
unityctl click MainCanvas/ShopWindow/BuyButton           # 默认对目标做射线遮挡验证
unityctl input MainCanvas/Login/NameField --text "Alice" --submit
unityctl set-value MainCanvas/Settings/VolumeSlider --value 0.5

unityctl gameplay list                                   # 查看可调用命令菜单（需先在 config.json 开启 gameplay.enabled）
unityctl gameplay invoke CheatManager.AddGold --args '{"amount": 100}'
```

`click`/`input`/`set-value` 直接派发 Unity 事件系统事件链，不是修改内部状态。`gameplay` 是零侵入调用游戏代码的通道（duck-typed attribute 或白名单），**默认关闭**，需在 `config.json` 显式开启且应只在测试/开发环境使用。

## 录制与自动化验证脚本（Scenario）

```bash
unityctl record start                                     # 录制手工点击/输入为 actions.jsonl
unityctl record stop

unityctl scenario from-recording actions.jsonl -o draft.json   # 从录制生成 scenario 草稿
unityctl scenario validate draft.json                     # 只做结构校验，不连接 Bridge
unityctl scenario run draft.json                          # 执行并生成 session + summary（含断言结果）
```

scenario 用 JSON 文件把「打开场景 → 操作 UI → 等待收敛 → 断言事实」固化成可重复执行、机器判定通过/失败的脚本；断言判定全部在 CLI 侧完成。字段结构见 `schemas/scenario.schema.json`。

## 性能采样与 Build 诊断

```bash
unityctl profile start                                    # 需 Play Mode，ProfilerRecorder 逐帧采样
# 让游戏运行一段时间……
unityctl profile stop                                     # 返回 metricsPath 及 avg/max/p95 汇总

unityctl build --target StandaloneOSX                     # 独立 batchmode 进程执行 Player 构建
```

`profile` 的采样值含 Editor 自身开销，只适合同机同项目改动前后的相对回归比较。`build` 会在独立 Unity 进程里执行（与正在运行的交互式 Editor 互斥，不会自动关闭），产物落在 `.unity-agent/builds/<buildId>/`，含 `build-report.json` 与 `build.log`。

## 项目健康检查

```bash
unityctl health                                            # 跑全部检查项
unityctl health --check compilation,missing_scripts        # 只跑指定项
```

四项独立检查：`compilation`（编译）、`missing_scripts`（已加载场景 + 全部 Prefab 资产的缺失脚本引用）、`build_scenes`（构建场景列表）、`packages`（UPM 包一致性）。`compilation`/`missing_scripts` 需要 Bridge，不可达时该项标记 `skipped` 而不计入整体失败。

以上各命令的完整参数、错误码和判读规则见内置的 [`unityctl` agent skill](src/unityctl/unityctl/skill_assets/unityctl/SKILL.md)（`unityctl skills init` 后也会安装到你的 Unity 项目里）。

## Agent Skill

CLI 内置了两份 agent skill（目录形态）：`unityctl`（参考手册，描述"改代码 → refresh → play → summary"的标准 Unity 验证流程）与 `unityctl-project-skill-creator`（引导为项目生成自定义 skill），供 Cursor、Claude Code 等 coding agent 学习使用。

在 Unity 项目根目录（或其子目录）安装：

```bash
unityctl skills init
```

默认安装到 Unity 项目的 `.agents/skills/` 下（每个 skill 一个目录）。可以用 `--target` 指定其他 skills 根目录，相对路径基于项目根目录解析，也支持绝对路径：

```bash
unityctl skills init --target .cursor/skills          # 安装到项目的 .cursor/skills/
unityctl skills init --target ~/.claude/skills        # 安装到全局目录（绝对路径不要求在 Unity 项目内执行）
```

行为语义与 `init` / schema 一致：

- `skills init`：目录已存在时不覆盖，返回 `already_installed`。
- `skills update`：与内置内容有差异时整目录覆盖刷新（未安装则直接安装，无差异返回 `up_to_date`）；升级 CLI 后运行一次即可同步 skill。

skill 的 frontmatter 中带有 `x-unityctl-version` 字段，记录生成它的 CLI 版本。

## 为你的项目编写自定义 skill

官方 `unityctl` skill 是通用参考手册，由 `unityctl skills update` 整目录覆盖刷新，**不要直接修改它**。项目专属的知识与流程放在你自己的 skill 里：

1. 在 `.agents/skills/<名字>/SKILL.md` 新建自己的 skill（`skills update` 永不触碰官方分发清单之外的目录）。
2. 自定义 skill 里写项目知识（界面约定、专属验证流程），组合调用 unityctl 命令即可；不要复述命令用法，用法以官方 skill 为准，避免两处过时。
3. 现成的数据扩展点：`scenario` JSON（可复跑验证脚本）、`.unity-agent/log-rules.json`（ignore 降噪 / watch 聚焦）、`gameplay` 的 attribute / whitelist（游戏侧暴露命令）。
4. 只想手动触发的流程，在 frontmatter 加 `disable-model-invocation: true`。
5. UI 定位类知识（界面根节点、识别规则、置顶判断）推荐用 `unityctl-project-skill-creator` 引导生成：对 agent 说「用 unityctl-project-skill-creator 为这个项目生成 UI 定位 skill」。

## 数据契约与示例

`schemas/` 固定了落盘文件和运行时文件的数据契约：

```text
schemas/config.schema.json
schemas/config.local.schema.json
schemas/bridge.schema.json
schemas/session.schema.json
schemas/unity-console-log.schema.json
schemas/summary.schema.json
schemas/log-rules.schema.json
schemas/actions.schema.json          # unityctl record 产出的 actions.jsonl
schemas/recording-meta.schema.json   # unityctl record 产出的 recording-meta.json
schemas/scenario.schema.json         # unityctl scenario run/validate 的输入文件
schemas/scenario-result.schema.json  # unityctl scenario run 产出的 scenario-result.json
schemas/metrics.schema.json          # unityctl profile 产出的 metrics.jsonl（逐行）
schemas/build-report.schema.json     # unityctl build 产出的 build-report.json
```

`examples/` 提供最小可读样例：

```text
examples/unity-project-manifest/manifest.json
examples/log-rules.json
examples/sessions/session.json
examples/sessions/unity-console.jsonl
examples/sessions/summary.json
examples/unity-agent-config/config.json
examples/unity-agent-config/config.local.json
examples/unity-agent-config/bridge.json
```

## 运行测试

Python 测试：

```bash
cd src/unityctl
uv run pytest tests -v
```

也可以从仓库根目录运行脚本：

```bash
scripts/run-python-tests.sh
```

Unity EditMode 测试，在仓库根目录下执行：

```bash
cd "$REPO_ROOT"
mkdir -p "$REPO_ROOT/.tmp/logs" "$REPO_ROOT/.tmp/test-results"

"$UNITY_BIN" \
  -batchmode \
  -projectPath "$REPO_ROOT/.tmp/unity-test-project" \
  -runTests \
  -testPlatform EditMode \
  -testResults "$REPO_ROOT/.tmp/test-results/editmode.xml" \
  -logFile "$REPO_ROOT/.tmp/logs/editmode.log"
```

Unity 测试命令**故意不传** `-quit` 参数；Unity 在测试运行写入结果 XML 后会自动退出。

也可以使用脚本运行。未设置 `UNITY_PROJECT` 时，脚本会使用仓库内
`.tmp/unity-test-project` 作为临时 Unity project：

```bash
export UNITY_BIN="/Applications/Unity/Hub/Editor/2022.3.62f2/Unity.app/Contents/MacOS/Unity"
scripts/run-unity-editmode-tests.sh
```

## 本地模拟正式安装

在发布前验证 Release 产物安装路径：

```bash
scripts/install-local.sh
```

可选传入 Unity 项目路径，脚本会把 manifest 依赖改为 `file:<tgz绝对路径>`：

```bash
scripts/install-local.sh /absolute/path/to/UnityProject
```

脚本会：

1. 打包 UPM `.tgz` 到 `.tmp/packages/`
2. 构建 Python wheel
3. 用 `uv tool install --force <wheel>` 安装 CLI
4. 打印 `unityctl --version` 验证结果

## 打包 UPM

从仓库根目录运行：

```bash
scripts/package-upm.sh
```

产物默认写入 `.tmp/packages/`，也可以通过 `DIST_DIR` 指定输出目录：

```bash
DIST_DIR="$REPO_ROOT/.tmp/release" scripts/package-upm.sh
```

### 发布流程

1. 在 `main` 分支执行版本升级脚本（会同步更新 Unity 包与 Python 工具版本、commit 并打 tag）：

```bash
scripts/bump-version.sh patch
# 或 minor / major
# 仅本地完成、不 push：scripts/bump-version.sh patch --no-push
```

2. 脚本默认 push `main` 与 `vX.Y.Z` tag；GitHub Actions 会自动：
   - 校验 tag 位于 `main` 历史上
   - 校验 tag 与 `package.json` / `pyproject.toml` / `__init__.py` 版本一致
   - 运行 Python 测试
   - 将包切出到 `upm` 分支，并创建 `upm/vX.Y.Z` tag
   - 创建 GitHub Release，附带 UPM `.tgz`、Python wheel 与 sdist

发布后，Unity 项目可通过以下方式引用：

```json
"com.mk.unity-agent-bridge": "https://github.com/mikko-ai/UnityRunBridge.git#upm/vX.Y.Z"
```

Python CLI 可从同一 Release 的 wheel 安装（见上文「从 GitHub Release 安装」）。
