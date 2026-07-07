# MCP for Unity 项目简介

> 参考来源：[CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp)（本地副本：`tmp_refs/unity-mcp`，版本约 v10.0.1-beta.5）  
> 文档站点：<https://coplaydev.github.io/unity-mcp/>  
> 许可证：MIT

## 概述

**MCP for Unity** 是一个开源桥接项目，通过 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/introduction) 将 AI 助手（Claude、Cursor、VS Code、Windsurf 等）与 Unity Editor 连接起来。开发者可以用自然语言让 LLM 直接操作编辑器：创建场景与 GameObject、编辑 C# 脚本、管理资源、运行测试、截图验证、性能分析、构建出包等。

项目由 [Coplay](https://www.coplay.dev/) 维护，与 Unity Technologies 无官方关联。当前提供约 **47 个 MCP 工具入口**，支持 Unity **2021.3 LTS 至 6.x**，Python **3.10+**（推荐通过 [`uv`](https://docs.astral.sh/uv/) / `uvx` 管理）。

## 架构

系统由两个主要代码库组成，通过 MCP 协议与 WebSocket/HTTP 协同工作：

```text
AI 助手（Claude / Cursor / VS Code 等）
        ↓ MCP 协议（stdio 或 HTTP）
Python MCP Server（Server/）
        ↓ WebSocket + HTTP
Unity Editor 插件（MCPForUnity/）
        ↓ Unity Editor API
场景、资源、脚本
```

### Python 侧三层结构

| 层级 | 位置 | 作用 |
|------|------|------|
| **MCP Tools** | `Server/src/services/tools/` | 暴露给 AI 的可调用工具（FastMCP） |
| **CLI Commands** | `Server/src/cli/commands/` | 面向开发者的终端命令（Click） |
| **Resources** | `Server/src/services/resources/` | 只读状态查询（如 editor state、scene、prefab 等） |

MCP 工具通过 WebSocket 调用 Unity；CLI 命令通过 HTTP 调用 Unity。两侧最终路由到 C# 侧同一套 `HandleCommand` 处理器。

### 传输模式

- **Stdio**：每个 MCP 客户端独立 Python 进程，适合单 agent 场景。
- **HTTP**：单一共享 Python 服务，WebSocket hub 位于 `/hub/plugin`，支持多 agent 与会话隔离；也是 Cursor、Claude Desktop 等客户端的默认推荐方式。

### 领域对称设计

Python MCP 工具与 C# Editor 工具一一对应，例如：

- `manage_material.py` ↔ `ManageMaterial.cs`
- `manage_gameobject.py` ↔ `ManageGameObject.cs`
- `read_console.py` ↔ `ReadConsole.cs`

工具通过反射自动注册：Python 侧用 `@mcp_for_unity_tool`，C# 侧用 `[McpForUnityTool]` 特性。

## 仓库结构

| 目录 | 说明 |
|------|------|
| `MCPForUnity/` | Unity Editor 包（`com.coplaydev.unity-mcp`），含 Bridge、工具实现、配置 UI |
| `Server/` | Python MCP 服务器，可独立发布到 PyPI（`mcpforunityserver`） |
| `unity-mcp-skill/` | 面向 AI agent 的操作指南与 workflow 参考 |
| `docs/` / `website/` | 文档与 Docusaurus 站点 |
| `tools/` | 发布脚本、版本检查、本地 harness、压力测试等 |
| `TestProjects/` | 测试用 Unity 项目 |
| `CustomTools/` | 自定义工具示例（如 Roslyn 运行时编译） |

## 主要能力

### 工具分组（Tool Groups）

工具按领域分组，默认仅启用 **core** 组；其余组（vfx、animation、ui、testing、probuilder、profiling 等）可在 Unity 窗口中按需开启：

- **场景与对象**：创建/修改 GameObject、查找对象、管理 Prefab、ProBuilder 网格
- **脚本**：创建脚本、`script_apply_edits` / `apply_text_edits`、Roslyn 语义校验
- **资源与材质**：纹理、材质、Shader、ScriptableObject、Package 管理
- **UI / 动画 / VFX**：UGUI、Animator、粒子等
- **测试与调试**：运行 Test Framework、`read_console`、截图、性能采样
- **v10 新增**：AI 资产生成（图片/模型导入等）

### MCP Resources（只读查询）

除 Tools 外，还提供 URI 形式的只读资源，例如：

- `mcpforunity://editor/state` — 编辑器就绪状态、是否在编译等
- `mcpforunity://project/tags` — 项目 Tag 列表
- `mcpforunity://scene/gameobject/{instance_id}` — GameObject 详情
- `mcpforunity://prefab/{encoded_path}` — Prefab 信息

推荐 workflow：**先读 Resource 了解上下文，再调用 Tool 执行操作，最后用 console / screenshot 验证**。

### 脚本校验

Unity 插件提供多级脚本校验（Basic → Strict），Strict 模式依赖 Roslyn 做完整语义分析。

### 高级特性

- **多 Unity 实例路由**：同时打开多个项目时，通过 instance 标识选择目标
- **Remote-hosted 模式**：HTTP 服务 + API Key 鉴权，支持团队共享或远程部署
- **batch_execute**：批量执行多个工具调用，减少往返延迟
- **Docker 部署**：提供 Dockerfile 与预构建镜像

## 安装与使用（简要）

1. **安装 Unity 包**：Package Manager → Add from git URL  
   `https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#main`
2. **配置 MCP 客户端**：`Window → MCP for Unity → Configure All Detected Clients`（一键配置 Cursor / VS Code 等）
3. **启动 Bridge**：在 MCP for Unity 窗口中 Start Bridge
4. **在 AI 客户端中发指令**：例如 *"在原点创建一个 Cube 并添加 Rigidbody"*

MCP 客户端典型 HTTP 配置：

```json
{
  "mcpServers": {
    "unityMCP": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

也可通过 PyPI 独立运行 Server：`uvx --from mcpforunityserver mcp-for-unity --transport http`

## 与 UnityRunBridge 的关系

两者都解决「让 AI / agent 与 Unity Editor 交互」的问题，但定位不同：

| 维度 | MCP for Unity | UnityRunBridge |
|------|---------------|----------------|
| **协议** | MCP（面向 LLM 客户端） | HTTP Bridge + CLI（面向通用 coding agent） |
| **能力范围** | 广：编辑、资源、测试、构建、资产生成等 | 窄：运行控制 + 运行观测（Play Mode、日志、session） |
| **客户端** | Cursor、Claude、VS Code 等 MCP 客户端 | `unityctl` CLI + agent skill |
| **设计重心** | 通用 Unity AI 开发助手 | 低侵入的运行验证闭环 |
| **状态确认** | 工具级操作，部分异步需 agent 自行 poll | CLI 内置状态收敛（轮询直到 Play/Compile 完成） |
| **会话审计** | 依赖 console / 截图等即时反馈 | 每次运行落盘 `session.json`、`unity-console.jsonl`、`summary.json` |

UnityRunBridge 将 MCP for Unity 作为**参考实现**研究其 Bridge 模式、工具设计与 agent workflow；当前阶段不追求复刻其全量编辑能力，而是优先做好「写完代码 → 启动 Unity → 验证运行结果」这一闭环。

## 参考价值

对 UnityRunBridge 有借鉴意义的部分：

1. **Bridge 分层**：Editor 插件 + 外部进程（Python）的分工方式
2. **Resource-first workflow**：先读状态再操作，减少盲目调用
3. **编译后验证**：脚本修改后等待 `is_compiling == false` 再查 console
4. **工具分组与 batch_execute**：控制 API 面、降低延迟
5. **多实例与握手发现**：多项目并行时的路由与连接管理思路
6. **Skill 文档**：`unity-mcp-skill/` 展示了如何为 agent 编写可操作的最佳实践

## 相关链接

- GitHub：<https://github.com/CoplayDev/unity-mcp>
- 文档：<https://coplaydev.github.io/unity-mcp/>
- PyPI：`mcpforunityserver`
- Discord：<https://discord.gg/y4p8KfzrN4>
- OpenUPM：`com.coplaydev.unity-mcp`
