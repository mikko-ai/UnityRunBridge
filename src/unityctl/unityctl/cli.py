import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from unityctl import __version__
from unityctl.build import BuildError, run_build
from unityctl.client import BridgeClient, BridgeClientError
from unityctl.config import (
    ConfigError,
    UNITY_AGENT_BRIDGE_PACKAGE_ID,
    default_bridge_package_ref,
    find_latest_session_path,
    find_unity_project_root,
    init_project_config,
    install_bridge_package,
    is_bridge_package_installed,
    read_json,
    resolve_effective_config,
    validate_project_config,
    write_json,
)
from unityctl.convergence import (
    ConvergenceEditorExited,
    ConvergenceFailed,
    ConvergenceTimeout,
    parse_utc_timestamp,
    poll_until,
)
from unityctl.discovery import (
    BridgeInfo,
    DiscoveryError,
    bridge_info_path,
    discover,
    is_pid_alive,
    is_unity_project_locked,
    read_bridge_info,
)
from unityctl.editor import start_editor
from unityctl.health import HealthError, run_health
from unityctl.jobs import JobEditorExited, JobFailed, JobTimeout, wait_for_job
from unityctl.scenario import (
    ScenarioContext,
    ScenarioValidationError,
    convert_recording_to_scenario,
    load_scenario,
    run_scenario,
    validate_scenario,
)
from unityctl.session import (
    create_session,
    format_time,
    mark_session_failed,
    update_session_status,
    utc_now,
)
from unityctl.skills import (
    DEFAULT_SKILLS_DIRNAME,
    SkillError,
    install_all_skills,
    resolve_skills_dir,
)
from unityctl.summary import build_summary, classify_log, load_log_rules, read_jsonl, write_summary


class CliError(RuntimeError):
    def __init__(self, code: str, message: str, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.extra = extra or {}


class _HelpFormatter(argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    pass


def _add_project_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        dest="project_path",
        metavar="PATH",
        help="Unity 项目根目录（默认从当前目录向上查找）",
    )


def _add_session_options(parser: argparse.ArgumentParser, required: bool = True) -> None:
    session = parser.add_mutually_exclusive_group(required=required)
    session.add_argument(
        "--session-path",
        metavar="PATH",
        help="session 目录的绝对路径（.unity-agent/sessions/<sessionId>/）",
    )
    session.add_argument(
        "--latest",
        action="store_true",
        help="使用最近创建的 session",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unityctl",
        description=(
            "通过 Unity Agent Bridge 控制 Unity Editor 的 CLI 工具。"
            "所有命令以 JSON 输出到 stdout；失败时 stderr 输出 {\"ok\": false, ...}。"
        ),
        epilog=(
            "示例:\n"
            "  unityctl init --yes\n"
            "  unityctl config validate\n"
            "  unityctl start\n"
            "  unityctl play --session login-flow --scene Assets/Scenes/Login.unity\n"
            "  unityctl stop --latest\n"
            "  unityctl click MainCanvas/StartButton\n"
            "  unityctl input MainCanvas/NameField --text \"Alice\" --submit\n"
            "  unityctl set-value MainCanvas/VolumeSlider --value 0.5\n"
            "  unityctl gameplay list\n"
            "  unityctl record start --latest\n"
            "  unityctl record stop\n"
            "  unityctl profile start --latest\n"
            "  unityctl profile stop\n"
            "  unityctl scenario validate login-flow.json\n"
            "  unityctl scenario run login-flow.json\n"
            "  unityctl build --target StandaloneOSX\n"
            "  unityctl health\n"
            "  unityctl doctor\n"
            "\n"
            "使用 unityctl <命令> --help 查看单个命令的详细参数。"
        ),
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"unityctl {__version__}")
    parser.add_argument(
        "--project",
        dest="global_project_path",
        metavar="PATH",
        help="Unity 项目根目录；可作为各子命令 --project 的全局默认值",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        title="命令",
        metavar="COMMAND",
    )

    init = subparsers.add_parser(
        "init",
        help="初始化 .unity-agent 配置目录",
        description=(
            "在 Unity 项目根目录创建 .unity-agent/config.json、config.local.json 和 schema 文件。"
            "同时检测 Packages/manifest.json 是否包含 bridge 包依赖；"
            "缺失时在交互终端中询问是否写入，或使用 --install-package 直接写入。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(init)
    init.add_argument(
        "--unity",
        dest="unity_path",
        metavar="PATH",
        help="Unity 可执行文件路径（写入 config.local.json）",
    )
    init.add_argument("--unity-version", help="Unity 版本号（写入 config.json）")
    init.add_argument(
        "--port",
        dest="preferred_port",
        type=int,
        default=17890,
        help="Bridge 期望监听端口",
    )
    init.add_argument(
        "--scene",
        dest="default_scene",
        metavar="PATH",
        help="默认场景路径，例如 Assets/Scenes/Main.unity",
    )
    init.add_argument(
        "--yes",
        action="store_true",
        help="跳过交互确认（脚本/CI 使用）",
    )
    init.add_argument(
        "--force",
        action="store_true",
        help="重新生成缺失的配置文件（不覆盖已有 config.json / config.local.json）",
    )
    package_group = init.add_mutually_exclusive_group()
    package_group.add_argument(
        "--install-package",
        action="store_true",
        help="若 Packages/manifest.json 缺少 bridge 包依赖，直接写入（不询问）",
    )
    package_group.add_argument(
        "--no-install-package",
        action="store_true",
        help="跳过 Packages/manifest.json 依赖检测与写入",
    )
    init.add_argument(
        "--package-ref",
        metavar="REF",
        help=(
            "写入 manifest 的依赖引用，例如 git URL 或 file: 路径"
            "（默认指向与 unityctl 版本一致的 upm tag）"
        ),
    )

    config = subparsers.add_parser(
        "config",
        help="查看或校验项目配置",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(config)
    config_subparsers = config.add_subparsers(
        dest="config_command",
        required=True,
        title="子命令",
        metavar="SUBCOMMAND",
    )
    config_subparsers.add_parser(
        "show",
        help="输出合并后的有效配置（项目配置 + 本机配置）",
        formatter_class=_HelpFormatter,
    )
    config_subparsers.add_parser(
        "validate",
        help="校验 config.json 与 config.local.json",
        formatter_class=_HelpFormatter,
    )
    set_local = config_subparsers.add_parser(
        "set-local",
        help="更新 config.local.json 中的单个字段",
        formatter_class=_HelpFormatter,
    )
    set_local.add_argument(
        "key",
        help="字段名，例如 unityExecutablePath",
    )
    set_local.add_argument(
        "value",
        help="字段值",
    )

    status = subparsers.add_parser(
        "status",
        help="查询 Unity Editor 当前状态",
        description="通过 Bridge 获取 editorState、编译结果、当前场景等信息。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(status)

    play = subparsers.add_parser(
        "play",
        help="进入 Play Mode",
        description=(
            "可选打开场景并创建 session 记录运行日志。"
            "未指定 --scene 时使用 config.json 中的 defaultScene；若也未配置则播放当前场景。"
            "默认等待进入 Play Mode；若存在编译错误则失败。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(play)
    play.add_argument(
        "--session",
        dest="session_name",
        metavar="NAME",
        help="创建 session 并记录 unity-console.jsonl（位于 .unity-agent/sessions/）",
    )
    play.add_argument(
        "--scene",
        dest="scene_path",
        metavar="PATH",
        help="进入 Play Mode 前打开的场景路径（覆盖 config.json 中的 defaultScene）",
    )
    play.add_argument("--task", default="", help="session 任务描述（写入 session.json）")
    play.add_argument(
        "--trigger",
        default="agent",
        help="session 触发来源（写入 session.json）",
    )
    play.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="等待收敛的超时秒数（默认读取 config.json 中的 playSeconds）",
    )
    play.add_argument(
        "--no-wait",
        action="store_true",
        help="发送 play 请求后立即返回，不等待进入 Play Mode",
    )

    stop = subparsers.add_parser(
        "stop",
        help="退出 Play Mode",
        description="可选关联 session：退出后生成 summary.json。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(stop)
    stop.add_argument(
        "--session-path",
        metavar="PATH",
        help="关联的 session 目录；与 --latest 二选一",
    )
    stop.add_argument(
        "--latest",
        action="store_true",
        help="关联最近创建的 session",
    )
    stop.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="等待退出 Play Mode 的超时秒数（默认读取 config.json 中的 stopSeconds）",
    )
    stop.add_argument(
        "--no-wait",
        action="store_true",
        help="发送 stop 请求后立即返回，不等待 Editor 回到 idle",
    )

    pause = subparsers.add_parser(
        "pause",
        help="暂停 Play Mode",
        description="暂停当前 Play Mode（等同 Editor 中的暂停按钮），用 resume 恢复。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(pause)

    resume = subparsers.add_parser(
        "resume",
        help="恢复 Play Mode",
        description="恢复被 pause 暂停的 Play Mode。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(resume)

    open_scene = subparsers.add_parser(
        "open-scene",
        help="在 Editor 中打开场景",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(open_scene)
    open_scene.add_argument(
        "scene_path",
        metavar="PATH",
        help="场景路径，例如 Assets/Scenes/Login.unity",
    )

    start = subparsers.add_parser(
        "start",
        help="启动 Unity Editor 进程",
        description="默认等待 Bridge 握手完成（写出 bridge.json 并可连接）。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(start)
    start.add_argument(
        "--unity",
        dest="unity_path",
        metavar="PATH",
        help="覆盖 config.local.json 中的 Unity 可执行文件路径",
    )
    start.add_argument(
        "--log-file",
        metavar="PATH",
        help="Editor 日志文件路径（默认 .unity-agent/unity-editor.log）",
    )
    start.add_argument(
        "--no-wait",
        action="store_true",
        help="启动进程后立即返回，不等待 Bridge 握手",
    )

    logs = subparsers.add_parser(
        "logs",
        help="读取 session 的 Unity 控制台日志",
        description=(
            "从 session 目录的 unity-console.jsonl 读取 Unity Console 日志，"
            "按时间顺序返回过滤后最近的 N 条（含 type、message、stackTrace、runIndex 等字段）。"
            "每条日志附带 line 字段（在 unity-console.jsonl 中的 1-based 行号），"
            "便于回到完整日志中查看上下文。runIndex 标记该日志属于第几轮 Play Mode 运行。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(logs)
    _add_session_options(logs)
    logs.add_argument(
        "--limit",
        type=int,
        default=100,
        metavar="N",
        help="返回过滤后最近的 N 条日志",
    )
    logs.add_argument(
        "--grep",
        metavar="TEXT",
        help="只返回 message 包含该子串的日志（不区分大小写）",
    )
    logs.add_argument(
        "--type",
        dest="types",
        metavar="TYPES",
        help="按日志类型过滤，逗号分隔（如 Error,Exception,Warning,Log,Assert）",
    )
    logs.add_argument(
        "--after-sequence",
        type=int,
        metavar="N",
        help="只返回 sequence 大于 N 的日志（用于跳过已读日志、只看增量）",
    )
    logs.add_argument(
        "--run",
        type=int,
        metavar="N",
        help="只返回第 N 轮 Play Mode 运行的日志（runIndex == N；0 表示首轮运行前的编辑期日志）",
    )
    logs.add_argument(
        "--include-events",
        action="store_true",
        help="包含 Bridge 写入的运行边界事件行（type=BridgeEvent，默认过滤）",
    )

    errors = subparsers.add_parser(
        "errors",
        help="读取 session 中的错误与阻塞日志",
        description="按 .unity-agent/log-rules.json 中的 ignore 规则过滤后返回 problem/blocking 级别条目。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(errors)
    _add_session_options(errors)

    summary = subparsers.add_parser(
        "summary",
        help="读取 session 的 summary.json",
        description=(
            "读取 session 的运行结果汇总。status 取值："
            "passed（无问题）、problem_detected（出现普通 Error 日志，需结合日志判断）、"
            "failed（出现 Exception/Assert 等 blocking problem，或进程级失败，"
            "原因见 failedReason）。runs 按 Play Mode 轮次分组统计；"
            "manualInterventionDetected 为 true 表示有人在 Editor 中手动重新进入过 "
            "Play Mode，结果可能混入非受控运行。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(summary)
    _add_session_options(summary)

    refresh = subparsers.add_parser(
        "refresh",
        help="触发脚本重编译并等待完成",
        description=(
            "触发 AssetDatabase.Refresh() 并轮询直到编译结束，"
            "返回 compilationSucceeded 与 compilationErrors。"
            "改完代码后用它验证编译是否通过。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(refresh)
    refresh.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="等待编译完成的超时秒数（默认读取 config.json 中的 playSeconds）",
    )

    doctor = subparsers.add_parser(
        "doctor",
        help="诊断项目配置与 Bridge 连通性",
        description="检查项目根目录、配置文件、UPM 包、bridge.json 和 Bridge HTTP 可达性。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(doctor)

    build = subparsers.add_parser(
        "build",
        help="独立 batchmode 进程构建 Player（不经过 Bridge）",
        description=(
            "spawn 一个新的 Unity batchmode 进程执行构建，与正在运行、供交互调试的 Editor 实例"
            "完全独立；两者不能同时持有同一个项目，构建前会检测 Temp/UnityLockfile 是否被占用。"
            "构建目标用 Unity 原生 -buildTarget 传递，报告写在 "
            ".unity-agent/builds/<buildId>/build-report.json。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(build)
    build.add_argument(
        "--target",
        metavar="TARGET",
        help="Unity 原生 BuildTarget 名，例如 StandaloneOSX/StandaloneWindows64/Android/iOS/WebGL；"
        "缺省使用项目当前 active build target（省略 -buildTarget 参数）",
    )
    build.add_argument(
        "--output",
        dest="output_path",
        metavar="PATH",
        help="构建产物路径（含文件名，平台相关扩展名需自己给对，如 .app/.exe/.apk）；"
        "缺省写到 .unity-agent/builds/<buildId>/Build/ 下按 target 推断的默认文件名",
    )
    build.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="等待构建进程结束的超时时间（秒），默认读取 config.json 的 timeouts.buildSeconds（3600）",
    )

    health = subparsers.add_parser(
        "health",
        help="项目健康检查（编译/缺失脚本/构建场景列表/包一致性）",
        description=(
            "doctor 回答『环境能不能跑』，health 回答『项目干不干净』：默认跑全部检查项，"
            "可用 --check 只跑指定项。需要 Bridge 的检查项在 Bridge 不可达时标记为 skipped 并说明原因，"
            "不计入整体失败。退出码：pass/warn 为 0，fail 为 1（CI 门禁友好）。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(health)
    health.add_argument(
        "--check",
        metavar="NAME[,NAME...]",
        help="只运行指定检查项（逗号分隔），可选：compilation,missing_scripts,build_scenes,packages；"
        "缺省运行全部",
    )
    health.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="compilation 检查等待编译完成、missing_scripts 检查等待 prefab 扫描 job 完成的超时时间（秒）",
    )

    hierarchy = subparsers.add_parser(
        "hierarchy",
        help="查询场景 Hierarchy 结构（只读）",
        description="通过 Bridge 的 /hierarchy/* 端点查询场景树，输出原样为 Bridge 的 JSON 信封。",
        formatter_class=_HelpFormatter,
    )
    _add_project_option(hierarchy)
    hierarchy_subparsers = hierarchy.add_subparsers(
        dest="hierarchy_command",
        required=True,
        title="子命令",
        metavar="SUBCOMMAND",
    )
    hierarchy_subparsers.add_parser(
        "roots",
        help="列出所有已加载场景（含 DontDestroyOnLoad）的根节点",
        formatter_class=_HelpFormatter,
    )

    hierarchy_tree = hierarchy_subparsers.add_parser(
        "tree",
        help="从指定节点向下遍历子树",
        formatter_class=_HelpFormatter,
    )
    hierarchy_tree.add_argument("path", help="节点 path 或 instanceId（纯数字视为 instanceId）")
    hierarchy_tree.add_argument("--scene", help="多场景同名 path 命中歧义时用于消歧")
    hierarchy_tree.add_argument("--depth", type=int, default=3, help="向下遍历层数，-1 为不限层")
    hierarchy_tree.add_argument("--page-size", type=int, dest="page_size", help="单页节点数（默认 50，上限 500）")
    hierarchy_tree.add_argument("--cursor", help="续扫游标（上次响应的 nextCursor）")

    hierarchy_find = hierarchy_subparsers.add_parser(
        "find",
        help="按过滤条件搜索节点（全 AND 组合）",
        formatter_class=_HelpFormatter,
    )
    hierarchy_find.add_argument("--name", help="精确匹配节点名")
    hierarchy_find.add_argument("--name-contains", dest="nameContains", help="节点名包含子串（不区分大小写）")
    hierarchy_find.add_argument("--name-regex", dest="nameRegex", help="节点名匹配 .NET 正则")
    hierarchy_find.add_argument("--path-glob", dest="pathGlob", help="path 通配（* 匹配一段，** 匹配多段）")
    hierarchy_find.add_argument("--component", help="组件短名或 FQN（含派生类）")
    hierarchy_find.add_argument("--interface", help="接口短名或 FQN（任一组件实现即匹配）")
    hierarchy_find.add_argument("--missing-script", dest="missingScript", action="store_true", help="只要含缺失脚本引用的节点")
    hierarchy_find.add_argument("--tag", help="按 tag 过滤")
    hierarchy_find.add_argument("--layer", help="按 layer 过滤（名字或数字）")
    hierarchy_find.add_argument("--under", help="限定子树的 path 或 instanceId")
    hierarchy_find.add_argument("--scene", help="限定场景名（含 DontDestroyOnLoad）")
    active_group = hierarchy_find.add_mutually_exclusive_group()
    active_group.add_argument("--active-only", dest="active", action="store_const", const="only", help="只要 activeInHierarchy 的节点")
    active_group.add_argument("--inactive-only", dest="active", action="store_const", const="none", help="只要非 activeInHierarchy 的节点")
    hierarchy_find.add_argument("--text-contains", dest="textContains", help="Text/TMP 文本包含子串（不区分大小写）")
    hierarchy_find.add_argument("--where", help="受限属性过滤：Component.property<op>value，op 为 = != > < >= <=")
    hierarchy_find.add_argument("--sort-by", dest="sortBy", metavar="Component.prop", help="按属性排序（在分页前）")
    hierarchy_find.add_argument("--desc", action="store_true", help="配合 --sort-by 降序排序")
    hierarchy_find.add_argument("--count", dest="countOnly", action="store_true", help="只返回命中数量，不返回节点列表")
    hierarchy_find.add_argument("--page-size", type=int, dest="page_size", help="单页节点数（默认 50，上限 500）")
    hierarchy_find.add_argument("--cursor", help="续扫游标（上次响应的 nextCursor）")

    hierarchy_ancestors = hierarchy_subparsers.add_parser(
        "ancestors",
        help="列出目标节点的祖先（近到远）",
        formatter_class=_HelpFormatter,
    )
    hierarchy_ancestors.add_argument("path", help="节点 path 或 instanceId")
    hierarchy_ancestors.add_argument("--scene", help="多场景同名 path 命中歧义时用于消歧")
    hierarchy_ancestors.add_argument("--component", help="只返回含该组件（含派生类）的祖先")

    hierarchy_inspect = hierarchy_subparsers.add_parser(
        "inspect",
        help="查看目标节点的完整组件/属性详情",
        formatter_class=_HelpFormatter,
    )
    hierarchy_inspect.add_argument("path", help="节点 path 或 instanceId")
    hierarchy_inspect.add_argument("--scene", help="多场景同名 path 命中歧义时用于消歧")

    snapshot = subparsers.add_parser(
        "snapshot",
        help="截取 Game View 截图（需 Play Mode）",
        description=(
            "通过 Bridge 的异步 job 截取当前 Game View 画面，落盘为 PNG 并等待 job 完成。"
            "受 config.json 中 capture.screenshot 配置项管控（总开关/配额/最大边长/agent 权限）。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(snapshot)
    snapshot.add_argument(
        "--reason",
        default="agent",
        help="截图触发原因，写入 capture 配额统计维度（默认 agent，即 agent 主动发起）",
    )
    snapshot.add_argument(
        "--max-long-edge",
        type=int,
        dest="max_long_edge",
        metavar="PIXELS",
        help="覆盖 config.json 中 capture.screenshot.maxLongEdge（单次调用生效）",
    )
    snapshot.add_argument(
        "--target-directory",
        dest="target_directory",
        metavar="PATH",
        help="覆盖输出目录（必须在 .unity-agent/sessions/ 或 .unity-agent/scratch/ 之下）；默认按当前 session 自动解析",
    )
    snapshot.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        metavar="SECONDS",
        help="等待截图 job 完成的超时秒数",
    )

    click_cmd = subparsers.add_parser(
        "click",
        help="点击 UGUI 节点（需 Play Mode）",
        description=(
            "通过 Bridge 的 /interaction/click 端点模拟指针点击。默认对目标节点 screenRect "
            "中心做射线检测：被遮挡返回 occluded（并附 blockedBy 指出遮挡者），命中链上没有 "
            "点击处理器返回 no_click_handler；--force 跳过射线检测，直接对目标节点派发事件链。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(click_cmd)
    click_cmd.add_argument("path", help="节点 path 或 instanceId")
    click_cmd.add_argument(
        "--force",
        action="store_true",
        help="跳过射线遮挡检测，直接对目标节点派发点击事件链",
    )
    click_cmd.add_argument("--scene", help="多场景同名 path 命中歧义时用于消歧")

    input_cmd = subparsers.add_parser(
        "input",
        help="向 InputField/TMP_InputField 写入文本（需 Play Mode）",
        description=(
            "通过 Bridge 的 /interaction/input 端点设置输入框文本"
            "（自然触发 onValueChanged）；--submit 额外触发 onEndEdit/onSubmit 并取消选中。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(input_cmd)
    input_cmd.add_argument("path", help="节点 path 或 instanceId")
    input_cmd.add_argument("--text", required=True, help="要写入的文本")
    input_cmd.add_argument(
        "--submit",
        action="store_true",
        help="写入后触发 onEndEdit/onSubmit 并取消选中",
    )
    input_cmd.add_argument("--scene", help="多场景同名 path 命中歧义时用于消歧")

    set_value_cmd = subparsers.add_parser(
        "set-value",
        help="设置 Slider/Toggle/Scrollbar/Dropdown/ScrollRect 的值（需 Play Mode）",
        description=(
            "通过 Bridge 的 /interaction/set-value 端点设值，经组件属性 setter 自然触发 "
            "onValueChanged。--value 按 JSON 解析（数字/布尔/对象），"
            "例如 --value 0.5、--value true、--value '{\"x\": 0.5, \"y\": 0.2}'。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(set_value_cmd)
    set_value_cmd.add_argument("path", help="节点 path 或 instanceId")
    set_value_cmd.add_argument(
        "--value",
        required=True,
        help="要设置的值，JSON 字面量（数字/布尔/对象）；非法 JSON 时按裸字符串传递",
    )
    set_value_cmd.add_argument(
        "--component",
        help="显式指定组件（节点上有多个可设值组件时必填），如 Slider/Toggle/Scrollbar/Dropdown/ScrollRect",
    )
    set_value_cmd.add_argument("--scene", help="多场景同名 path 命中歧义时用于消歧")

    gameplay = subparsers.add_parser(
        "gameplay",
        help="列出/调用零侵入 gameplay 命令（需 Play Mode，默认关闭）",
        description=(
            "通过 Bridge 的 /gameplay/* 端点发现并调用游戏侧暴露的命令。两条发现通道："
            "duck-typed attribute（游戏代码用 AgentCommandAttribute 标注公开静态方法，"
            "不依赖本包）与 config.json 里 gameplay.whitelist 配置的完全限定方法名白名单。"
            "受 config.json 的 gameplay.enabled 总开关控制，默认 false（安全默认）。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(gameplay)
    gameplay_subparsers = gameplay.add_subparsers(
        dest="gameplay_command",
        required=True,
        title="子命令",
        metavar="SUBCOMMAND",
    )
    gameplay_subparsers.add_parser(
        "list",
        help="列出当前可调用的命令菜单",
        formatter_class=_HelpFormatter,
    )
    gameplay_invoke = gameplay_subparsers.add_parser(
        "invoke",
        help="调用一个命令",
        formatter_class=_HelpFormatter,
    )
    gameplay_invoke.add_argument("name", help="命令名（attribute 命令的短名，或白名单里的完全限定名）")
    gameplay_invoke.add_argument(
        "--args",
        default=None,
        metavar="JSON",
        help='参数，JSON 对象字符串，例如 \'{"amount": 100}\'（默认空对象）',
    )

    record = subparsers.add_parser(
        "record",
        help="录制 UGUI 语义动作（actions.jsonl，需 Play Mode）",
        description=(
            "通过 Bridge 的 /recording/* 端点录制点击（按 hierarchy path 记录，非坐标）与"
            "输入框失焦，写出 actions.jsonl 与 recording-meta.json。"
            "domain reload / 退出 Play Mode 会打断录制，stop/status 会如实报告 interrupted。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(record)
    record_subparsers = record.add_subparsers(
        dest="record_command",
        required=True,
        title="子命令",
        metavar="SUBCOMMAND",
    )
    record_start = record_subparsers.add_parser(
        "start",
        help="开始录制",
        formatter_class=_HelpFormatter,
    )
    _add_session_options(record_start, required=False)
    record_start.add_argument(
        "--target-directory",
        metavar="PATH",
        help="直接指定输出目录（须在 .unity-agent/sessions 或 .unity-agent/scratch 下）；"
        "与 --session-path/--latest 三选一，都不给时由 Bridge 按当前 session 自动解析",
    )
    record_subparsers.add_parser(
        "stop",
        help="停止录制，返回 actionsPath/actionCount/interrupted",
        formatter_class=_HelpFormatter,
    )
    record_subparsers.add_parser(
        "status",
        help="查询当前录制状态",
        formatter_class=_HelpFormatter,
    )

    profile = subparsers.add_parser(
        "profile",
        help="采样 ProfilerRecorder 逐帧计数器（metrics.jsonl，需 Play Mode）",
        description=(
            "通过 Bridge 的 /profiling/* 端点采样固定计数器集（frameTimeMs/gcAllocBytes/"
            "drawCalls/setPassCalls/triangles/totalMemoryBytes/gcMemoryBytes），写出 metrics.jsonl。"
            "计数器在当前 Unity 版本/渲染管线下缺失时记入 unavailableMetrics，不静默返回 0。"
            "Editor 内采样含 Editor 开销，绝对值不代表真机性能，只用于同机同项目改动前后的相对回归比较。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(profile)
    profile_subparsers = profile.add_subparsers(
        dest="profile_command",
        required=True,
        title="子命令",
        metavar="SUBCOMMAND",
    )
    profile_start = profile_subparsers.add_parser(
        "start",
        help="开始采样",
        formatter_class=_HelpFormatter,
    )
    _add_session_options(profile_start, required=False)
    profile_start.add_argument(
        "--target-directory",
        metavar="PATH",
        help="直接指定输出目录（须在 .unity-agent/sessions 或 .unity-agent/scratch 下）；"
        "与 --session-path/--latest 三选一，都不给时由 Bridge 按当前 session 自动解析",
    )
    profile_subparsers.add_parser(
        "stop",
        help="停止采样，返回 metricsPath/frameCount/interrupted/aggregates（avg/max/p95）",
        formatter_class=_HelpFormatter,
    )
    profile_subparsers.add_parser(
        "status",
        help="查询当前采样状态",
        formatter_class=_HelpFormatter,
    )

    scenario = subparsers.add_parser(
        "scenario",
        help="运行/校验 scenario 文件，或从录制生成草稿",
        description=(
            "scenario 是线性步骤表：控制（open-scene/play/stop/pause/resume）+ "
            "操作（click/input/set-value/invoke）+ 观测（screenshot/snapshot）+ "
            "收敛（wait-for）+ 断言（assert，四选一 source：ui/log/gameplay/metric）。"
            "run 会创建独立 session，产出 artifacts/scenario-result.json 并把断言结果并入 summary.json。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(scenario)
    scenario_subparsers = scenario.add_subparsers(
        dest="scenario_command",
        required=True,
        title="子命令",
        metavar="SUBCOMMAND",
    )
    scenario_run = scenario_subparsers.add_parser(
        "run",
        help="执行 scenario 文件（需 Bridge 可达）",
        formatter_class=_HelpFormatter,
    )
    scenario_run.add_argument("file", metavar="FILE", help="scenario JSON 文件路径")
    scenario_run.add_argument(
        "--session",
        dest="session_name",
        metavar="NAME",
        help="session 名字（默认取 scenario 的 name 字段）",
    )
    scenario_run.add_argument(
        "--timeout-scale",
        type=float,
        default=1.0,
        metavar="F",
        help="全局缩放 wait-for/assert/收敛等待的超时秒数（CI 环境偏慢时可调大）",
    )

    scenario_validate = scenario_subparsers.add_parser(
        "validate",
        help="只做字段/结构校验，不连接 Bridge、不创建 session",
        formatter_class=_HelpFormatter,
    )
    scenario_validate.add_argument("file", metavar="FILE", help="scenario JSON 文件路径")

    scenario_from_recording = scenario_subparsers.add_parser(
        "from-recording",
        help="把 record 产出的 actions.jsonl 转成 scenario 草稿（不含断言）",
        formatter_class=_HelpFormatter,
    )
    scenario_from_recording.add_argument("actions_path", metavar="ACTIONS_JSONL", help="actions.jsonl 路径")
    scenario_from_recording.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="写出草稿到指定文件；不给则只在 stdout 的 JSON 里返回 scenario 字段",
    )
    scenario_from_recording.add_argument(
        "--name",
        metavar="NAME",
        help="草稿的 scenario name（默认根据 recording-meta.json 的 sessionId 生成）",
    )

    skills = subparsers.add_parser(
        "skills",
        help="安装或更新内置 agent skills（目录形态）",
        description=(
            "把 CLI 内置的官方 skills（unityctl 参考手册、project skill creator）"
            f"安装到项目的 skills 目录，默认 {DEFAULT_SKILLS_DIRNAME}/。"
        ),
        formatter_class=_HelpFormatter,
    )
    _add_project_option(skills)
    skills_subparsers = skills.add_subparsers(
        dest="skills_command",
        required=True,
        title="子命令",
        metavar="SUBCOMMAND",
    )
    skills_init = skills_subparsers.add_parser(
        "init",
        help="安装 skills（目录已存在时不覆盖）",
        formatter_class=_HelpFormatter,
    )
    skills_update = skills_subparsers.add_parser(
        "update",
        help="把 skills 刷新为当前 CLI 版本内置内容（有差异时整目录覆盖；无差异返回 up_to_date；未安装则直接安装）",
        formatter_class=_HelpFormatter,
    )
    for sub in (skills_init, skills_update):
        sub.add_argument(
            "--target",
            metavar="PATH",
            default=None,
            help=(
                "skills 根目录；相对路径基于 Unity 项目根目录解析，也可用绝对路径"
                f"（默认 {DEFAULT_SKILLS_DIRNAME}）"
            ),
        )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.project_path = getattr(args, "project_path", None) or args.global_project_path

    try:
        payload = dispatch(args)
        print_json(payload)
        return 0 if payload.get("ok", True) else 1
    except (CliError, BridgeClientError, DiscoveryError, ConfigError, ValueError) as exc:
        # 信封统一：CLI 自身产生的错误也使用 message 字段，与 Bridge 的
        # {"ok", "code", "message"} 响应结构一致（历史上曾用 "error"，破坏性变更）。
        payload = {"ok": False, "code": _error_code(exc), "message": str(exc)}
        if isinstance(exc, CliError):
            payload.update(exc.extra)
        print_json(payload, stream=sys.stderr)
        return 1


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    handlers = {
        "init": cmd_init,
        "config": cmd_config,
        "status": cmd_status,
        "play": cmd_play,
        "stop": cmd_stop,
        "pause": cmd_pause,
        "resume": cmd_resume,
        "open-scene": cmd_open_scene,
        "start": cmd_start,
        "logs": cmd_logs,
        "errors": cmd_errors,
        "summary": cmd_summary,
        "refresh": cmd_refresh,
        "doctor": cmd_doctor,
        "build": cmd_build,
        "health": cmd_health,
        "hierarchy": cmd_hierarchy,
        "snapshot": cmd_snapshot,
        "click": cmd_click,
        "input": cmd_input,
        "set-value": cmd_set_value,
        "gameplay": cmd_gameplay,
        "record": cmd_record,
        "profile": cmd_profile,
        "scenario": cmd_scenario,
        "skills": cmd_skills,
    }
    handler = handlers.get(args.command)
    if handler is None:
        raise CliError("not_found", f"unsupported command: {args.command}")
    return handler(args)


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    project = find_unity_project_root(args.project_path or Path.cwd())
    if not args.yes:
        confirm_init(project, force=args.force)
    result = init_project_config(
        project_path=project,
        unity_path=args.unity_path,
        unity_version=args.unity_version,
        preferred_port=args.preferred_port,
        default_scene=args.default_scene,
        force=args.force,
    )

    package_ref = args.package_ref or default_bridge_package_ref(__version__)
    package_action, package_installed = _handle_bridge_package_install(
        project=result.project_path,
        package_ref=package_ref,
        install=args.install_package,
        skip=args.no_install_package,
        assume_yes=args.yes,
    )

    next_steps = [
        "Edit .unity-agent/config.local.json and set unityExecutablePath",
        "Run unityctl config validate",
        "Run unityctl start",
    ]
    if not package_installed:
        next_steps.insert(
            0,
            f"Add {UNITY_AGENT_BRIDGE_PACKAGE_ID} to Packages/manifest.json "
            "(or rerun unityctl init --install-package)",
        )

    return {
        "ok": True,
        "code": "ok",
        "projectPath": str(result.project_path),
        "configPath": str(result.config_path),
        "localConfigPath": str(result.local_config_path),
        "preferredPort": result.preferred_port,
        "packageInstalled": package_installed,
        "packageAction": package_action,
        "packageRef": package_ref if package_action == "installed" else None,
        "alreadyInitialized": bool(result.kept_paths),
        "createdPaths": [str(path) for path in result.created_paths],
        "keptPaths": [str(path) for path in result.kept_paths],
        "updatedIgnore": result.updated_ignore,
        "nextSteps": next_steps,
    }


def _handle_bridge_package_install(
    project: Path,
    package_ref: str,
    install: bool,
    skip: bool,
    assume_yes: bool,
) -> tuple[str, bool]:
    """检测 Packages/manifest.json 中的 bridge 包依赖，按需写入。

    返回 (packageAction, packageInstalled)。packageAction 取值：
    already_installed / installed / declined / skipped。
    """
    if is_bridge_package_installed(project):
        return "already_installed", True
    if skip:
        return "skipped", False
    if not install:
        # 未显式指定时：交互终端里询问用户；非交互（含 --yes）不擅自改 manifest。
        if assume_yes or not sys.stdin.isatty():
            return "skipped", False
        if not confirm_install_package(project, package_ref):
            return "declined", False
    manifest_path = install_bridge_package(project, package_ref)
    print(f"已写入 {manifest_path}", file=sys.stderr)
    return "installed", True


def cmd_config(args: argparse.Namespace) -> dict[str, Any]:
    if args.config_command == "validate":
        project = find_unity_project_root(args.project_path or Path.cwd())
        result = validate_project_config(project)
        return {
            "ok": result.ok,
            "code": "ok" if result.ok else "invalid_request",
            "projectPath": str(result.project_path),
            "errors": [
                {"field": issue.field, "message": issue.message} for issue in result.errors
            ],
            "warnings": [
                {"field": issue.field, "message": issue.message} for issue in result.warnings
            ],
        }

    effective = resolve_effective_config(project_path=args.project_path)
    if args.config_command == "show":
        return {
            "ok": True,
            "code": "ok",
            "projectPath": str(effective.project_path),
            "preferredPort": effective.preferred_port,
            "unityVersion": effective.unity_version,
            "unityExecutablePath": (
                str(effective.unity_executable_path)
                if effective.unity_executable_path
                else None
            ),
            "defaultScene": effective.default_scene,
            "timeouts": {
                "playSeconds": effective.timeouts.play_seconds,
                "stopSeconds": effective.timeouts.stop_seconds,
                "startEditorSeconds": effective.timeouts.start_editor_seconds,
            },
            "sources": {
                "projectConfig": str(effective.project_config_path),
                "localConfig": str(effective.local_config_path),
            },
        }
    if args.config_command == "set-local":
        payload = read_json(effective.local_config_path)
        payload[args.key] = args.value
        write_json(effective.local_config_path, payload)
        return {"ok": True, "code": "ok", args.key: args.value}

    raise CliError("not_found", f"unsupported config command: {args.config_command}")


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    return client.get_status()


def cmd_pause(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    return client.post("pause")


def cmd_resume(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    return client.post("resume")


def cmd_open_scene(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    return client.open_scene(args.scene_path)


def cmd_play(args: argparse.Namespace) -> dict[str, Any]:
    effective = resolve_effective_config(project_path=args.project_path)
    scene_path = args.scene_path or effective.default_scene
    timeout_seconds = (
        args.timeout if args.timeout is not None else effective.timeouts.play_seconds
    )

    info = discover(effective.project_path)
    client = BridgeClient(info.base_url, info.token)
    status = client.get_status()

    # 正在编译/更新时先等它结束，再基于最新状态判断编译结果：
    # 此刻的 compilationSucceeded 是上一轮编译的陈旧值，直接快速失败会误杀正在修复的编译。
    if status.get("editorState") in {"compiling", "updating"}:
        try:
            wait_result = poll_until(
                effective.project_path,
                predicate=lambda current: current.get("editorState") not in {"compiling", "updating"},
                timeout_seconds=timeout_seconds,
                initial_info=info,
            )
        except ConvergenceTimeout as exc:
            raise CliError("timeout", "等待 Unity 编译或资源更新完成超时") from exc
        except ConvergenceEditorExited as exc:
            raise CliError("editor_exited", str(exc)) from exc
        status = wait_result.status
        info, client = _refresh_client(info, client, wait_result.info)

    if not status.get("compilationSucceeded", True):
        raise CliError(
            "compilation_failed",
            "Unity 项目当前存在编译错误，无法进入 Play Mode",
            extra={"compilationErrors": status.get("compilationErrors", [])},
        )

    session = None
    if args.session_name:
        session = create_session(
            project_path=effective.project_path,
            name=args.session_name,
            scene_path=scene_path,
            trigger=args.trigger,
            task=args.task,
            created_at=utc_now(),
            editor_pid=info.pid,
            unity_version=info.unity_version,
        )
        client.start_session(session.session_id, str(session.session_path))

    try:
        if scene_path:
            open_scene_response = client.post("open-scene", {"scenePath": scene_path})
            if not open_scene_response.get("ok", False):
                raise CliError(
                    open_scene_response.get("code", "invalid_request"),
                    open_scene_response.get("message", "打开场景失败"),
                )
            if not args.no_wait:
                scene_result = poll_until(
                    effective.project_path,
                    predicate=lambda current: current.get("activeScenePath") == scene_path,
                    timeout_seconds=timeout_seconds,
                    initial_info=info,
                )
                info, client = _refresh_client(info, client, scene_result.info)

        request_time = utc_now().replace(microsecond=0)
        play_response = client.post("play")
        if not play_response.get("ok", False) and play_response.get("code") != "already_playing":
            raise CliError(
                play_response.get("code", "internal_error"),
                play_response.get("message", "进入 Play Mode 失败"),
            )

        def predicate(current_status: dict[str, Any]) -> bool:
            editor_state = current_status.get("editorState")
            if editor_state == "playing":
                return True
            if editor_state in {"enteringPlay", "compiling", "updating"}:
                return False
            if editor_state == "idle":
                finished_at = current_status.get("compilationFinishedAt") or ""
                if (
                    finished_at
                    and not current_status.get("compilationSucceeded", True)
                    and parse_utc_timestamp(finished_at) >= request_time
                ):
                    raise ConvergenceFailed("compilation_failed", status=current_status)
            return False

        if args.no_wait:
            payload: dict[str, Any] = {
                "ok": True,
                "code": play_response.get("code", "ok"),
                "play": play_response,
            }
            if session is not None:
                update_session_status(session.session_path, "running", started_at=format_time(utc_now()))
                payload["sessionId"] = session.session_id
                payload["sessionPath"] = str(session.session_path)
            return payload

        poll_result = poll_until(
            effective.project_path,
            predicate=predicate,
            timeout_seconds=timeout_seconds,
            initial_info=info,
        )
    except CliError as exc:
        if session is not None:
            _abort_bridge_session(client)
            _finalize_failed_session(session.session_path, effective.project_path, exc.code)
        raise
    except ConvergenceFailed as exc:
        if session is not None:
            _abort_bridge_session(client)
            _finalize_failed_session(session.session_path, effective.project_path, exc.reason)
        raise CliError(
            exc.reason,
            "编译失败，无法进入 Play Mode" if exc.reason == "compilation_failed" else exc.reason,
            extra={"compilationErrors": (exc.status or {}).get("compilationErrors", [])},
        ) from exc
    except ConvergenceTimeout as exc:
        if session is not None:
            _abort_bridge_session(client)
            _finalize_failed_session(session.session_path, effective.project_path, "timeout")
        raise CliError("timeout", "等待进入 Play Mode 超时") from exc
    except ConvergenceEditorExited as exc:
        if session is not None:
            _finalize_failed_session(session.session_path, effective.project_path, "editor_exited")
        raise CliError("editor_exited", str(exc)) from exc

    payload: dict[str, Any] = {"ok": True, "code": "ok", "status": poll_result.status}
    if session is not None:
        update_session_status(session.session_path, "running", started_at=format_time(utc_now()))
        payload["sessionId"] = session.session_id
        payload["sessionPath"] = str(session.session_path)
    return payload


def cmd_stop(args: argparse.Namespace) -> dict[str, Any]:
    effective = resolve_effective_config(project_path=args.project_path)
    timeout_seconds = (
        args.timeout if args.timeout is not None else effective.timeouts.stop_seconds
    )

    info = discover(effective.project_path)
    client = BridgeClient(info.base_url, info.token)

    session_path = None
    if args.session_path or args.latest:
        session_path = resolve_session_path(args, effective.project_path)

    stop_response = client.post("stop")
    if not stop_response.get("ok", False) and stop_response.get("code") != "already_stopped":
        raise CliError(
            stop_response.get("code", "internal_error"),
            stop_response.get("message", "退出 Play Mode 失败"),
        )

    result: dict[str, Any] = {"ok": True, "code": stop_response.get("code", "ok"), "stop": stop_response}

    if not args.no_wait:
        try:
            poll_result = poll_until(
                effective.project_path,
                predicate=lambda current: current.get("editorState") == "idle",
                timeout_seconds=timeout_seconds,
                initial_info=info,
            )
            result["status"] = poll_result.status
            info, client = _refresh_client(info, client, poll_result.info)
        except ConvergenceTimeout as exc:
            if session_path is not None:
                _abort_bridge_session(client)
                _finalize_failed_session(session_path, effective.project_path, "timeout")
            raise CliError("timeout", "等待退出 Play Mode 超时") from exc
        except ConvergenceEditorExited as exc:
            if session_path is not None:
                _finalize_failed_session(session_path, effective.project_path, "editor_exited")
            raise CliError("editor_exited", str(exc)) from exc

    end_response = client.end_session()
    result["sessionEnd"] = end_response

    if session_path is not None:
        update_session_status(session_path, "stopped", ended_at=format_time(utc_now()))
        summary_payload = build_summary(session_path, load_log_rules(effective.project_path))
        write_summary(session_path, summary_payload)
        result["summary"] = summary_payload

    return result


def cmd_start(args: argparse.Namespace) -> dict[str, Any]:
    effective = resolve_effective_config(project_path=args.project_path, unity_path=args.unity_path)
    project_path = effective.project_path

    info: BridgeInfo | None = None
    try:
        candidate = discover(project_path)
        BridgeClient(candidate.base_url, candidate.token).get_status()
        info = candidate
    except (DiscoveryError, BridgeClientError):
        info = None

    if info is not None:
        return {
            "ok": True,
            "code": "already_running",
            "pid": info.pid,
            "projectPath": str(project_path),
            "unityExecutablePath": (
                str(effective.unity_executable_path)
                if effective.unity_executable_path
                else None
            ),
            "logFile": None,
            "bridgeReady": True,
            "bridgeUrl": info.base_url,
            "unityVersion": info.unity_version,
        }

    if is_unity_project_locked(project_path):
        raise CliError(
            "editor_already_running",
            "检测到该 Unity 项目已被另一个 Editor 实例占用（Temp/UnityLockfile），"
            "但 Bridge 尚未就绪，可能卡在多实例提示框或正在握手中。"
            "请先处理已有的 Unity 窗口（关闭弹窗或退出该实例）后再运行 unityctl start。",
        )

    unity_executable = effective.unity_executable_path
    if unity_executable is None:
        raise CliError(
            "invalid_request",
            "Unity executable path is required. 请编辑 .unity-agent/config.local.json 或运行 "
            'unityctl config set-local unityExecutablePath "..."',
        )
    log_file = (
        Path(args.log_file).expanduser()
        if args.log_file
        else effective.project_path / ".unity-agent" / "unity-editor.log"
    )
    log_file.parent.mkdir(parents=True, exist_ok=True)
    process = start_editor(str(unity_executable), effective.project_path, log_file)

    payload: dict[str, Any] = {
        "ok": True,
        "code": "ok",
        "pid": process.pid,
        "projectPath": str(effective.project_path),
        "unityExecutablePath": str(unity_executable),
        "logFile": str(log_file),
        "bridgeReady": False,
    }

    if not args.no_wait:
        handshake_info = wait_for_handshake(
            effective.project_path,
            expected_pid=process.pid,
            timeout_seconds=effective.timeouts.start_editor_seconds,
        )
        payload["bridgeReady"] = True
        payload["bridgeUrl"] = handshake_info.base_url
        payload["unityVersion"] = handshake_info.unity_version

    return payload


def cmd_logs(args: argparse.Namespace) -> dict[str, Any]:
    project_path = _resolve_optional_project(args)
    session_path = resolve_session_path(args, project_path)
    rows = read_jsonl(session_path / "unity-console.jsonl")
    # line 是该条日志在 unity-console.jsonl 中的 1-based 行号，
    # 过滤后仍保留，便于回到完整日志中查看前后上下文。
    numbered = [{"line": index, **row} for index, row in enumerate(rows, start=1)]

    filtered = numbered
    if not args.include_events:
        filtered = [row for row in filtered if row.get("type") != "BridgeEvent"]
    if args.run is not None:
        filtered = [row for row in filtered if row.get("runIndex") == args.run]
    if args.grep:
        needle = args.grep.lower()
        filtered = [
            row for row in filtered if needle in str(row.get("message", "")).lower()
        ]
    if args.types:
        wanted = {item.strip().lower() for item in args.types.split(",") if item.strip()}
        filtered = [
            row for row in filtered if str(row.get("type", "")).lower() in wanted
        ]
    if args.after_sequence is not None:
        filtered = [
            row
            for row in filtered
            if isinstance(row.get("sequence"), int)
            and row["sequence"] > args.after_sequence
        ]

    return {
        "ok": True,
        "code": "ok",
        "totalCount": len(numbered),
        "matchedCount": len(filtered),
        "logs": filtered[-args.limit :],
    }


def cmd_errors(args: argparse.Namespace) -> dict[str, Any]:
    project_path = _resolve_optional_project(args)
    session_path = resolve_session_path(args, project_path)
    rules = load_log_rules(project_path)
    rows = read_jsonl(session_path / "unity-console.jsonl")
    problems = []
    for line, row in enumerate(rows, start=1):
        severity = classify_log(row, rules)
        if severity in {"problem", "blocking"}:
            problems.append({"line": line, **row, "severity": severity})
    return {"ok": True, "code": "ok", "errors": problems}


def cmd_summary(args: argparse.Namespace) -> dict[str, Any]:
    project_path = _resolve_optional_project(args)
    session_path = resolve_session_path(args, project_path)
    summary_path = session_path / "summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload.setdefault("ok", True)
    return payload


def cmd_refresh(args: argparse.Namespace) -> dict[str, Any]:
    effective = resolve_effective_config(project_path=args.project_path)
    timeout_seconds = (
        args.timeout if args.timeout is not None else effective.timeouts.play_seconds
    )

    info = discover(effective.project_path)
    client = BridgeClient(info.base_url, info.token)
    refresh_response = client.refresh()
    if not refresh_response.get("ok", False):
        raise CliError(
            refresh_response.get("code", "internal_error"),
            refresh_response.get("message", "触发 refresh 失败"),
        )

    try:
        poll_result = poll_until(
            effective.project_path,
            predicate=lambda current: current.get("editorState") not in {"compiling", "updating"},
            timeout_seconds=timeout_seconds,
            initial_info=info,
        )
    except ConvergenceTimeout as exc:
        raise CliError("timeout", "等待编译完成超时") from exc
    except ConvergenceEditorExited as exc:
        raise CliError("editor_exited", str(exc)) from exc

    status = poll_result.status
    return {
        "ok": True,
        "code": "ok",
        "compilationSucceeded": status.get("compilationSucceeded", True),
        "compilationErrors": status.get("compilationErrors", []),
        "editorState": status.get("editorState"),
    }


def cmd_hierarchy(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    _require_capability(client, "hierarchy")

    if args.hierarchy_command == "roots":
        return client.hierarchy_roots()

    if args.hierarchy_command == "tree":
        return client.hierarchy_tree(
            path=args.path,
            scene=args.scene,
            depth=args.depth,
            pageSize=args.page_size,
            cursor=args.cursor,
        )

    if args.hierarchy_command == "find":
        return client.hierarchy_find(
            name=args.name,
            nameContains=args.nameContains,
            nameRegex=args.nameRegex,
            pathGlob=args.pathGlob,
            component=args.component,
            interface=args.interface,
            missingScript=args.missingScript,
            tag=args.tag,
            layer=args.layer,
            under=args.under,
            scene=args.scene,
            active=args.active,
            textContains=args.textContains,
            where=args.where,
            sortBy=args.sortBy,
            order="desc" if args.desc else None,
            countOnly=args.countOnly,
            pageSize=args.page_size,
            cursor=args.cursor,
        )

    if args.hierarchy_command == "ancestors":
        return client.hierarchy_ancestors(path=args.path, scene=args.scene, component=args.component)

    if args.hierarchy_command == "inspect":
        return client.hierarchy_inspect(path=args.path, scene=args.scene)

    raise CliError("not_found", f"unsupported hierarchy command: {args.hierarchy_command}")


def cmd_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    _require_capability(client, "capture")

    start_response = client.capture_screenshot(
        reason=args.reason,
        max_long_edge=args.max_long_edge,
        target_directory=args.target_directory,
    )
    if not start_response.get("ok", False):
        raise CliError(
            start_response.get("code", "internal_error"),
            start_response.get("message", "启动截图 job 失败"),
        )

    job_id = start_response.get("jobId")
    try:
        job = wait_for_job(project_path, job_id, timeout_seconds=args.timeout, initial_info=info)
    except JobFailed as exc:
        raise CliError(
            exc.job.get("errorCode", "capture_failed"),
            exc.job.get("errorMessage", "截图失败"),
        ) from exc
    except JobTimeout as exc:
        raise CliError("timeout", str(exc)) from exc
    except JobEditorExited as exc:
        raise CliError("editor_exited", str(exc)) from exc

    result = job.get("result") or {}
    return {
        "ok": True,
        "code": "ok",
        "jobId": job_id,
        "path": result.get("path"),
        "width": result.get("width"),
        "height": result.get("height"),
    }


def cmd_click(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    _require_capability(client, "interaction")
    return client.interaction_click(path=args.path, force=args.force, scene=args.scene)


def cmd_input(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    _require_capability(client, "interaction")
    return client.interaction_input(path=args.path, text=args.text, submit=args.submit, scene=args.scene)


def cmd_set_value(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    _require_capability(client, "interaction")
    value = _parse_value_arg(args.value)
    return client.interaction_set_value(path=args.path, value=value, component=args.component, scene=args.scene)


def cmd_gameplay(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    _require_capability(client, "gameplay")

    if args.gameplay_command == "list":
        return client.gameplay_list()

    if args.gameplay_command == "invoke":
        try:
            parsed_args = json.loads(args.args) if args.args else {}
        except json.JSONDecodeError as exc:
            raise CliError("invalid_argument", f"--args 不是合法 JSON：{exc}") from exc
        if not isinstance(parsed_args, dict):
            raise CliError("invalid_argument", "--args 必须是 JSON 对象，例如 '{\"amount\": 100}'")
        return client.gameplay_invoke(args.name, parsed_args)

    raise CliError("not_found", f"unsupported gameplay command: {args.gameplay_command}")


def cmd_record(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    _require_capability(client, "recording")

    if args.record_command == "start":
        target_directory = getattr(args, "target_directory", None)
        if getattr(args, "latest", False) or getattr(args, "session_path", None):
            if target_directory:
                raise CliError(
                    "invalid_argument", "--target-directory 与 --session-path/--latest 三选一"
                )
            session_path = resolve_session_path(args, project_path)
            target_directory = str(session_path / "artifacts")
        return client.recording_start(target_directory=target_directory)

    if args.record_command == "stop":
        return client.recording_stop()

    if args.record_command == "status":
        return client.recording_status()

    raise CliError("not_found", f"unsupported record command: {args.record_command}")


def cmd_profile(args: argparse.Namespace) -> dict[str, Any]:
    project_path = args.project_path or Path.cwd()
    info = discover(project_path)
    client = BridgeClient(info.base_url, info.token)
    _require_capability(client, "profiling")

    if args.profile_command == "start":
        target_directory = getattr(args, "target_directory", None)
        if getattr(args, "latest", False) or getattr(args, "session_path", None):
            if target_directory:
                raise CliError(
                    "invalid_argument", "--target-directory 与 --session-path/--latest 三选一"
                )
            session_path = resolve_session_path(args, project_path)
            target_directory = str(session_path / "artifacts")
        return client.profiling_start(target_directory=target_directory)

    if args.profile_command == "stop":
        return client.profiling_stop()

    if args.profile_command == "status":
        return client.profiling_status()

    raise CliError("not_found", f"unsupported profile command: {args.profile_command}")


def cmd_scenario(args: argparse.Namespace) -> dict[str, Any]:
    if args.scenario_command == "validate":
        scenario_data = load_scenario(args.file)
        errors = validate_scenario(scenario_data)
        return {"ok": not errors, "code": "ok" if not errors else "invalid_scenario", "errors": errors}

    if args.scenario_command == "from-recording":
        try:
            scenario_data = convert_recording_to_scenario(args.actions_path, name=args.name)
        except ScenarioValidationError as exc:
            raise CliError("invalid_scenario", str(exc), extra={"errors": exc.errors}) from exc
        payload: dict[str, Any] = {"ok": True, "code": "ok", "scenario": scenario_data}
        if args.output:
            output_path = Path(args.output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(scenario_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            payload["outputPath"] = str(output_path)
        return payload

    if args.scenario_command == "run":
        return _cmd_scenario_run(args)

    raise CliError("not_found", f"unsupported scenario command: {args.scenario_command}")


def _cmd_scenario_run(args: argparse.Namespace) -> dict[str, Any]:
    effective = resolve_effective_config(project_path=args.project_path)
    scenario_data = load_scenario(args.file)
    errors = validate_scenario(scenario_data)
    if errors:
        raise CliError("invalid_scenario", "; ".join(errors), extra={"errors": errors})

    info = discover(effective.project_path)
    client = BridgeClient(info.base_url, info.token)

    session_name = args.session_name or scenario_data.get("name") or "scenario"
    session = create_session(
        project_path=effective.project_path,
        name=session_name,
        scene_path=None,
        trigger="scenario",
        task=scenario_data.get("description", ""),
        created_at=utc_now(),
        editor_pid=info.pid,
        unity_version=info.unity_version,
    )
    client.start_session(session.session_id, str(session.session_path))
    update_session_status(session.session_path, "running", started_at=format_time(utc_now()))

    ctx = ScenarioContext(
        client=client,
        session_path=session.session_path,
        capture_config=_load_capture_config(effective.project_path),
        timeout_scale=args.timeout_scale,
        screenshot_target_directory=str(session.session_path / "artifacts"),
    )

    try:
        result = run_scenario(scenario_data, ctx)
    except ScenarioValidationError as exc:
        _abort_bridge_session(client)
        _finalize_failed_session(session.session_path, effective.project_path, "invalid_scenario")
        raise CliError("invalid_scenario", "; ".join(exc.errors)) from exc
    except Exception as exc:  # noqa: BLE001 - 任何未预期异常都要保证 session 收尾落盘，而不是留下悬空 session
        _abort_bridge_session(client)
        _finalize_failed_session(session.session_path, effective.project_path, "scenario_execution_error")
        raise CliError("scenario_execution_error", str(exc)) from exc

    end_response = client.end_session()
    update_session_status(session.session_path, "stopped", ended_at=format_time(utc_now()))

    artifacts_dir = session.session_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "scenario-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    summary_payload = build_summary(
        session.session_path, load_log_rules(effective.project_path), scenario_result=result
    )
    write_summary(session.session_path, summary_payload)

    return {
        "ok": result["status"] == "passed",
        "code": "ok" if result["status"] == "passed" else "scenario_failed",
        "sessionId": session.session_id,
        "sessionPath": str(session.session_path),
        "sessionEnd": end_response,
        "scenario": result,
        "summary": summary_payload,
    }


def _load_capture_config(project_path: Path) -> dict[str, Any]:
    config_path = Path(project_path) / ".unity-agent" / "config.json"
    payload = read_json(config_path)
    screenshot_config = ((payload.get("capture") or {}).get("screenshot") or {})
    return {
        "onAssertFailure": screenshot_config.get("onAssertFailure", True),
        "onScenarioStep": screenshot_config.get("onScenarioStep", True),
    }


def _parse_value_arg(raw: str) -> Any:
    """--value 优先按 JSON 解析（覆盖数字/布尔/对象/数组等 set-value 支持的形态）；
    不是合法 JSON 时退化为裸字符串透传给 Bridge，由 Bridge 侧按组件类型校验报错。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def cmd_doctor(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": passed, "detail": detail})

    project_path: Path | None = None
    try:
        project_path = find_unity_project_root(args.project_path or Path.cwd())
        add("project_root", True, str(project_path))
    except ConfigError as exc:
        add("project_root", False, str(exc))

    effective = None
    if project_path is not None:
        try:
            effective = resolve_effective_config(project_path=project_path)
            add("config_json", True, str(effective.project_config_path))
        except (json.JSONDecodeError, ValueError) as exc:
            add("config_json", False, str(exc))

    if effective is not None:
        executable = effective.unity_executable_path
        if executable is not None and executable.is_file():
            add("unity_executable_path", True, str(executable))
        else:
            add("unity_executable_path", False, str(executable) if executable else "未配置")

    if project_path is not None:
        add(
            "upm_package_installed",
            is_bridge_package_installed(project_path),
            UNITY_AGENT_BRIDGE_PACKAGE_ID,
        )

    info: BridgeInfo | None = None
    if project_path is not None:
        try:
            info = read_bridge_info(project_path)
            add("bridge_json", True, str(bridge_info_path(project_path)))
        except DiscoveryError as exc:
            add("bridge_json", False, str(exc))

    bridge_reachable = False
    if info is not None:
        alive = is_pid_alive(info.pid)
        add("editor_pid_alive", alive, f"pid={info.pid}")
        if alive:
            try:
                BridgeClient(info.base_url, info.token).get_status()
                bridge_reachable = True
                add("bridge_reachable", True, info.base_url)
            except BridgeClientError as exc:
                add("bridge_reachable", False, str(exc))
        else:
            add("bridge_reachable", False, "editor process not alive")

    if project_path is not None:
        locked = is_unity_project_locked(project_path)
        if bridge_reachable:
            add(
                "project_lock",
                True,
                f"项目由存活且可达的 Editor 进程持有（pid={info.pid}）",
            )
        elif locked:
            add(
                "project_lock",
                False,
                "检测到 Temp/UnityLockfile 被占用（或无法确认未被占用），但没有可达的 Bridge；"
                "Unity 可能卡在多实例提示框、正在启动/编译中，或锁文件权限异常。"
                "此时执行 unityctl start 会导致新实例卡死，建议先手动确认 Unity 窗口状态",
            )
        else:
            add("project_lock", True, "项目未被占用，可以运行 unityctl start")

    overall_ok = all(check["ok"] for check in checks)
    return {"ok": overall_ok, "code": "ok" if overall_ok else "internal_error", "checks": checks}


def cmd_build(args: argparse.Namespace) -> dict[str, Any]:
    effective = resolve_effective_config(project_path=args.project_path)
    timeout_seconds = (
        args.timeout if args.timeout is not None else effective.timeouts.build_seconds
    )

    try:
        result = run_build(
            project_path=effective.project_path,
            unity_executable=effective.unity_executable_path,
            target=args.target,
            output_path=args.output_path,
            timeout_seconds=timeout_seconds,
        )
    except BuildError as exc:
        raise CliError(exc.code, str(exc)) from exc

    report = result.report
    return {
        "ok": result.ok,
        "code": "ok" if result.ok else "build_failed",
        "buildId": result.build_id,
        "result": result.result,
        "reportPath": str(result.report_path),
        "logPath": str(result.log_path),
        "outputPath": report.get("outputPath") or str(result.output_path),
        "sizeBytes": report.get("sizeBytes"),
        "durationMs": report.get("durationMs"),
        "errors": report.get("errors", []),
        "warnings": report.get("warnings", []),
        "reportSource": report.get("reportSource"),
    }


def cmd_health(args: argparse.Namespace) -> dict[str, Any]:
    effective = resolve_effective_config(project_path=args.project_path)
    timeout_seconds = args.timeout if args.timeout is not None else effective.timeouts.play_seconds
    checks = [name.strip() for name in args.check.split(",")] if args.check else None

    try:
        result = run_health(
            project_path=effective.project_path,
            effective=effective,
            checks=checks,
            timeout_seconds=timeout_seconds,
        )
    except HealthError as exc:
        raise CliError(exc.code, str(exc)) from exc

    return {
        "ok": result["ok"],
        "code": "ok" if result["ok"] else "health_check_failed",
        "status": result["status"],
        "checks": result["checks"],
    }


# 聚合 code 取"变更程度最高"的 action（索引越小优先级越高）
_SKILL_ACTION_PRIORITY = ["installed", "updated", "already_installed", "up_to_date"]


def cmd_skills(args: argparse.Namespace) -> dict[str, Any]:
    # 绝对路径 --target 不依赖项目根目录，找不到项目也允许安装
    project_path: Path | None = None
    try:
        project_path = find_unity_project_root(args.project_path or Path.cwd())
    except ConfigError:
        pass

    try:
        skills_dir = resolve_skills_dir(project_path, args.target)
        results = install_all_skills(
            skills_dir,
            version=__version__,
            overwrite=args.skills_command == "update",
        )
    except SkillError as exc:
        raise CliError("invalid_request", str(exc)) from exc

    entries: list[dict[str, Any]] = []
    for result in results:
        entry: dict[str, Any] = {
            "name": result.name,
            "action": result.action,
            "skillPath": str(result.skill_path),
        }
        if result.previous_version is not None and result.previous_version != result.version:
            entry["previousVersion"] = result.previous_version
        entries.append(entry)

    payload: dict[str, Any] = {
        "ok": True,
        "code": min((r.action for r in results), key=_SKILL_ACTION_PRIORITY.index),
        "version": __version__,
        "skills": entries,
    }
    if any(r.action == "already_installed" for r in results):
        payload["hint"] = "已存在的 skill 未被覆盖；如需刷新为当前版本内容请运行 unityctl skills update"
    return payload


def _require_capability(client: BridgeClient, capability: str) -> None:
    """新命令（hierarchy/capture/interaction/gameplay/recording/profiling 等）执行前
    调用，缺失能力时给出明确的降级提示，而不是让请求以 404/not_found 失败。"""
    capabilities_response = client.get_capabilities()
    capabilities = capabilities_response.get("capabilities", [])
    if capability not in capabilities:
        raise CliError(
            "bridge_capability_missing",
            f"bridge 版本过旧，缺少 {capability} 能力，请升级 UPM 包",
        )


def _refresh_client(
    info: BridgeInfo, client: Any, latest_info: BridgeInfo | None
) -> tuple[BridgeInfo, Any]:
    """收敛轮询期间若发生 domain reload，bridge.json 可能被覆盖写出新端口，
    以 poll_until 返回的最新握手信息为准重建 client。"""
    if latest_info is None or latest_info == info:
        return info, client
    return latest_info, BridgeClient(latest_info.base_url, latest_info.token)


def _abort_bridge_session(client: Any) -> None:
    """失败路径下尽力通知 Unity 侧结束 session，让日志文件落盘并停止继续写入；
    通知失败不影响本地的失败记录。"""
    try:
        client.end_session()
    except BridgeClientError:
        pass


def _finalize_failed_session(session_path: Path, project_path: Path, reason: str) -> None:
    mark_session_failed(session_path, reason)
    summary_payload = build_summary(session_path, load_log_rules(project_path))
    write_summary(session_path, summary_payload)


def _resolve_optional_project(args: argparse.Namespace) -> Path:
    try:
        effective = resolve_effective_config(project_path=args.project_path)
        return effective.project_path
    except ConfigError:
        if args.project_path:
            raise
        return Path.cwd()


def _error_code(exc: Exception) -> str:
    if isinstance(exc, CliError):
        return exc.code
    if isinstance(exc, BridgeClientError):
        return exc.code
    if isinstance(exc, DiscoveryError):
        return exc.code
    return "internal_error"


def print_json(payload: dict[str, Any], stream: Any = None) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream or sys.stdout)


def confirm_init(project_path: Path, force: bool = False) -> None:
    if not sys.stdin.isatty():
        raise ValueError("init 需要确认项目路径；在脚本中请添加 --yes")
    action = "重新生成缺失或已有配置" if force else "初始化缺失配置"
    print(f"将为以下 Unity 项目{action}：", file=sys.stderr)
    print(str(project_path), file=sys.stderr)
    answer = input("是否继续？[y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise ValueError("用户取消 init")


def confirm_install_package(project_path: Path, package_ref: str) -> bool:
    print(
        f"检测到 {project_path / 'Packages' / 'manifest.json'} 中缺少 "
        f"{UNITY_AGENT_BRIDGE_PACKAGE_ID} 依赖。",
        file=sys.stderr,
    )
    print(f"将写入引用：{package_ref}", file=sys.stderr)
    answer = input("是否写入 Packages/manifest.json？[y/N] ").strip().lower()
    return answer in {"y", "yes"}


def resolve_session_path(args: argparse.Namespace, project_path: Path) -> Path:
    if getattr(args, "latest", False):
        return find_latest_session_path(project_path)
    if args.session_path:
        return Path(args.session_path).expanduser().resolve()
    raise ValueError("--session-path or --latest is required")


def wait_for_handshake(
    project_path: Path,
    expected_pid: int,
    timeout_seconds: float,
    poll_interval: float = 0.5,
) -> BridgeInfo:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while True:
        try:
            info = discover(project_path)
            if info.pid == expected_pid:
                return info
        except DiscoveryError as exc:
            last_error = exc
        if time.monotonic() > deadline:
            detail = f"：{last_error}" if last_error else ""
            raise CliError("timeout", f"等待 Unity Editor 完成握手超时{detail}")
        time.sleep(poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
