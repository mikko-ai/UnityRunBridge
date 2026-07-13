# unityctl Agent Gitignore Relocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `unityctl init` 把本机/运行时产物的忽略规则写入 `.unity-agent/.gitignore`，不再污染项目根 `.gitignore`。

**Architecture:** 复用现有 `append_gitignore_entry`；仅把目标路径改为 `agent_dir / ".gitignore"`，条目改为相对 `.unity-agent/` 的路径。`config validate` 同步检查该文件。根 `.gitignore` 完全不碰。

**Tech Stack:** Python 3、pytest、现有 `unityctl.config` 模块

## Global Constraints

- 不修改、不清理项目根 `.gitignore`（含旧条目）。
- 不改 `InitResult.updated_ignore` / CLI `updatedIgnore` 字段名。
- 追加策略保持「缺失才补、不删已有行」。
- 忽略文件必须名为 `.gitignore`（Git 原生子目录 ignore）。
- 注释与日志优先中文（见 `AGENTS_RULE.md`）。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `src/unityctl/unityctl/config.py` | `init_project_config` 写 ignore；`validate_project_config` 检查 ignore |
| `src/unityctl/tests/test_config.py` | 单元测试：init / validate / append helper |
| `src/unityctl/tests/test_cli.py` | CLI `init --yes` 集成断言 |
| `README.md` | 用户说明：ignore 位置 |
| `docs/project-notes.md` | 设计笔记：init 行为与建议忽略列表 |

不新增文件；不拆分 `config.py`。

---

### Task 1: init 写入 `.unity-agent/.gitignore`

**Files:**
- Modify: `src/unityctl/tests/test_config.py:99-122`
- Modify: `src/unityctl/unityctl/config.py:196-211`
- Test: `src/unityctl/tests/test_config.py`

**Interfaces:**
- Consumes: `append_gitignore_entry(path, entry) -> bool`；常量 `LOCAL_CONFIG_FILENAME`、`BRIDGE_INFO_FILENAME`、`SESSIONS_DIRNAME`、`SCRATCH_DIRNAME`、`BUILDS_DIRNAME`
- Produces: `init_project_config` 向 `.unity-agent/.gitignore` 追加相对路径条目；`updated_ignore` 语义不变

- [ ] **Step 1: 改写失败测试（期望 agent 目录 ignore，且不碰根文件）**

把 `test_init_project_config_updates_gitignore_for_all_local_artifacts` 改为：

```python
def test_init_project_config_updates_gitignore_for_all_local_artifacts(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    root_gitignore = project / ".gitignore"
    root_gitignore.write_text("Library/\n", encoding="utf-8")

    init_project_config(project_path=project)

    ignored = (project / ".unity-agent" / ".gitignore").read_text(encoding="utf-8")
    assert "config.local.json" in ignored
    assert "sessions/" in ignored
    assert "bridge.json" in ignored
    assert "scratch/" in ignored
    assert "builds/" in ignored
    assert root_gitignore.read_text(encoding="utf-8") == "Library/\n"
```

`test_append_gitignore_entry_adds_missing_line_once` 保持通用 helper 测试即可；可把示例 entry 改成相对路径以贴近新用法（可选，不强制）：

```python
def test_append_gitignore_entry_adds_missing_line_once(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("Library/\n", encoding="utf-8")

    append_gitignore_entry(gitignore, "config.local.json")
    append_gitignore_entry(gitignore, "config.local.json")

    assert gitignore.read_text(encoding="utf-8").splitlines() == [
        "Library/",
        "config.local.json",
    ]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd src/unityctl && python -m pytest tests/test_config.py::test_init_project_config_updates_gitignore_for_all_local_artifacts -v`

Expected: FAIL（读的是 `.unity-agent/.gitignore` 但文件尚未创建，或内容仍是旧路径写到根 `.gitignore`）

- [ ] **Step 3: 最小实现**

在 `init_project_config` 中，把 ignore 写入段替换为：

```python
    gitignore_path = agent_dir / ".gitignore"
    updated_local_ignore = append_gitignore_entry(
        gitignore_path, LOCAL_CONFIG_FILENAME
    )
    updated_sessions_ignore = append_gitignore_entry(
        gitignore_path, f"{SESSIONS_DIRNAME}/"
    )
    updated_bridge_ignore = append_gitignore_entry(
        gitignore_path, BRIDGE_INFO_FILENAME
    )
    updated_scratch_ignore = append_gitignore_entry(
        gitignore_path, f"{SCRATCH_DIRNAME}/"
    )
    updated_builds_ignore = append_gitignore_entry(
        gitignore_path, f"{BUILDS_DIRNAME}/"
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd src/unityctl && python -m pytest tests/test_config.py::test_init_project_config_updates_gitignore_for_all_local_artifacts tests/test_config.py::test_append_gitignore_entry_adds_missing_line_once -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/unityctl/tests/test_config.py src/unityctl/unityctl/config.py
git commit -m "$(cat <<'EOF'
feat: write init ignore rules to .unity-agent/.gitignore

EOF
)"
```

---

### Task 2: validate 检查 `.unity-agent/.gitignore`

**Files:**
- Modify: `src/unityctl/unityctl/config.py:387-395`
- Modify: `src/unityctl/tests/test_config.py`（新增测试）
- Test: `src/unityctl/tests/test_config.py`

**Interfaces:**
- Consumes: `validate_project_config(project_path) -> ValidationResult`；`LOCAL_CONFIG_FILENAME`
- Produces: 缺失 `config.local.json` 忽略规则时，`warnings` 含 `field="gitignore"`；不再读根 `.gitignore`

- [ ] **Step 1: 写失败测试**

在 `test_config.py` 追加：

```python
def test_validate_project_config_warns_when_agent_gitignore_missing_local_config(tmp_path):
    project = make_unity_project(tmp_path / "Game")
    unity = tmp_path / "Unity"
    unity.write_text("", encoding="utf-8")
    init_project_config(project_path=project, unity_path=unity)
    (project / ".unity-agent" / ".gitignore").write_text("sessions/\n", encoding="utf-8")

    result = validate_project_config(project)

    assert result.ok is True
    assert any(
        issue.field == "gitignore" and "config.local.json" in issue.message
        for issue in result.warnings
    )


def test_validate_project_config_does_not_warn_when_agent_gitignore_has_local_config(
    tmp_path,
):
    project = make_unity_project(tmp_path / "Game")
    unity = tmp_path / "Unity"
    unity.write_text("", encoding="utf-8")
    init_project_config(project_path=project, unity_path=unity)

    result = validate_project_config(project)

    assert result.ok is True
    assert all(issue.field != "gitignore" for issue in result.warnings)
```

若现有 validate 测试依赖根 `.gitignore` 才不报警，一并按新语义调整（以本 Task 两个测试为准）。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd src/unityctl && python -m pytest tests/test_config.py::test_validate_project_config_warns_when_agent_gitignore_missing_local_config tests/test_config.py::test_validate_project_config_does_not_warn_when_agent_gitignore_has_local_config -v`

Expected: 至少一个 FAIL（仍检查根 `.gitignore` 或文案路径不对）

- [ ] **Step 3: 最小实现**

把 `validate_project_config` 末尾的 gitignore 检查替换为：

```python
    gitignore = project / ".unity-agent" / ".gitignore"
    ignored = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    if LOCAL_CONFIG_FILENAME not in ignored:
        warnings.append(
            ValidationIssue(
                "gitignore",
                f"建议忽略 .unity-agent/{LOCAL_CONFIG_FILENAME}，避免提交本机路径",
            )
        )
```

- [ ] **Step 4: 跑相关测试确认通过**

Run: `cd src/unityctl && python -m pytest tests/test_config.py -v`

Expected: PASS（全部 `test_config.py`）

- [ ] **Step 5: Commit**

```bash
git add src/unityctl/tests/test_config.py src/unityctl/unityctl/config.py
git commit -m "$(cat <<'EOF'
feat: validate local-config ignore via .unity-agent/.gitignore

EOF
)"
```

---

### Task 3: CLI 断言与文档同步

**Files:**
- Modify: `src/unityctl/tests/test_cli.py:777`
- Modify: `README.md:149-157`
- Modify: `docs/project-notes.md:175-183` 与 `301-318`
- Test: `src/unityctl/tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1 的 init 行为（`.unity-agent/.gitignore` 相对路径条目）
- Produces: CLI/文档与实现一致

- [ ] **Step 1: 更新 CLI 测试断言**

将 `test_cli.py` 中对应断言改为：

```python
    assert "config.local.json" in (
        project / ".unity-agent" / ".gitignore"
    ).read_text()
```

- [ ] **Step 2: 跑 CLI 测试确认失败后实现（仅断言变更，实现已在 Task 1）**

Run: `cd src/unityctl && python -m pytest tests/test_cli.py -k "init_yes" -v`

Expected: 改断言前 FAIL（读根 `.gitignore`）；改断言后 PASS。

- [ ] **Step 3: 更新 README**

在 `unityctl init` 会创建列表中加入 `.unity-agent/.gitignore`，并把「应被 `.gitignore` 忽略」改成指向 agent 内 ignore：

```markdown
`unityctl init` 会创建：

```text
.unity-agent/config.json
.unity-agent/config.local.json
.unity-agent/schemas/*.json
.unity-agent/.gitignore
```

如果已经初始化，`init` 只补缺失文件，不会覆盖已有的 `config.json` / `config.local.json`（内置 schema 文件除外，它们总是被刷新）。`config.json` 保存可提交的项目配置，例如 Unity 版本、Bridge 期望端口和超时时间。`config.local.json` 保存本机配置，例如 Unity 可执行文件路径，由 `.unity-agent/.gitignore` 忽略（`init` 会维护该文件，缺失才补）。
```

- [ ] **Step 4: 更新 `docs/project-notes.md`**

行为规则中的：

```text
- 补 `.gitignore` 中缺失的 `.unity-agent/config.local.json`、...
```

改为：

```text
- 补 `.unity-agent/.gitignore` 中缺失的 `config.local.json`、`sessions/`、`bridge.json`、`scratch/`、`builds/`（不改动项目根 `.gitignore`）。
```

建议忽略区块改为：

```text
建议忽略（由 `.unity-agent/.gitignore` 管理，相对该目录）：

config.local.json
sessions/
bridge.json
scratch/
builds/
```

（`init` 会自动把这几条补进 `.unity-agent/.gitignore`，缺失才补，不会重复添加或删除用户自定义内容；不修改项目根 `.gitignore`。）

- [ ] **Step 5: 跑全量相关测试**

Run: `cd src/unityctl && python -m pytest tests/test_config.py tests/test_cli.py -k "init or gitignore or validate_project" -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/unityctl/tests/test_cli.py README.md docs/project-notes.md
git commit -m "$(cat <<'EOF'
docs: document .unity-agent/.gitignore for init ignore rules

EOF
)"
```

---

## Spec Coverage Checklist

| Spec 要求 | Task |
|-----------|------|
| 写入 `.unity-agent/.gitignore` 相对路径条目 | Task 1 |
| 不碰根 `.gitignore` | Task 1 测试显式断言 |
| `updatedIgnore` 字段名不变 | Task 1（未改 `InitResult`） |
| validate 检查 agent gitignore | Task 2 |
| 更新测试 | Task 1–3 |
| 更新 README / project-notes | Task 3 |
| 不做根文件清理/迁移 | 全计划未包含 |
