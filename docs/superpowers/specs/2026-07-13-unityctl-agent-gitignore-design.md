# unityctl init 忽略规则迁入 `.unity-agent/.gitignore`

日期：2026-07-13
状态：设计定稿，待实现

## 一、背景与问题

`unityctl init` 当前把本机/运行时产物的忽略规则追加到 **Unity 项目根目录的 `.gitignore`**：

```text
.unity-agent/config.local.json
.unity-agent/sessions/
.unity-agent/bridge.json
.unity-agent/scratch/
.unity-agent/builds/
```

这会污染项目自己的 ignore 文件，把 unityctl 内部约定混进仓库通用配置。目标是：忽略规则放在 `.unity-agent/` 下，由该目录自包含管理，不再改动项目根 `.gitignore`。

## 二、方案

采用 Git 原生的**子目录 `.gitignore`**：在 `.unity-agent/.gitignore` 中写入相对该目录的规则。Git 会自动读取并生效，无需在根 `.gitignore` 再写任何条目。

目标文件内容：

```gitignore
config.local.json
bridge.json
sessions/
scratch/
builds/
```

## 三、行为约定

1. **写入位置**：`project/.unity-agent/.gitignore`（不再写 `project/.gitignore`）。
2. **追加策略**：与现有 `append_gitignore_entry` 一致——缺失才追加，不覆盖、不删除已有行。
3. **根 `.gitignore`**：完全不碰。已初始化项目若根目录仍有旧条目，由用户自行清理（不做自动迁移、不做删除）。
4. **`updatedIgnore`**：语义不变——只要 `.unity-agent/.gitignore` 有任一新条目被写入，即记为 `true`。
5. **`config validate`**：检查 `.unity-agent/.gitignore` 是否包含 `config.local.json`；缺失时给出警告。不再检查根 `.gitignore`。

## 四、代码改动范围

| 位置 | 改动 |
|------|------|
| `init_project_config`（`config.py`） | `gitignore_path = agent_dir / ".gitignore"`；条目改为相对路径 |
| `validate_project_config`（`config.py`） | 读取并校验 `.unity-agent/.gitignore`；警告文案同步 |
| `append_gitignore_entry` | 保持通用 helper，不改语义 |

## 五、测试与文档

- 更新 `src/unityctl/tests/test_config.py`、`test_cli.py`：断言改为读 `.unity-agent/.gitignore` 与相对路径条目。
- 更新 `README.md`、`docs/project-notes.md`：说明 init 维护的是 `.unity-agent/.gitignore`，不再写根 `.gitignore`。

## 六、明确不做

- 不从根 `.gitignore` 移除旧条目。
- 不提供单独的迁移命令或交互提示去清理根文件。
- 不改 `InitResult` / CLI JSON 字段名（仍用 `updatedIgnore`）。
- 不引入非 `.gitignore` 的自定义忽略文件名。
