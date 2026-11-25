# AGENTS.md

本文件为 AI 辅助开发工具的入口配置，具体的行为规则请参阅 [AGENTS_RULE.md](./AGENTS_RULE.md)。

开始开发前，请先读 [Agent 开发交接](./docs/agent-handoff.md)，确认当前范围、代码入口、回归命令和后续优先级。旧计划仅用于回查设计，不作为当前任务清单。

## 版本规则（CLI 与 Unity UPM 同步）

- **按发布批次升版，不按命令、提交或 PR 数量累加。** 以上一个正式 `vX.Y.Z` 标签为基线：整批只有 Bug 修复用 **Patch**，有兼容的新功能用 **Minor**（无论批内有多少新功能或修复）。破坏性变更单独确认 Major。同一批候选已满足升版要求时，后续改动沿用候选版本；仅在整批变更级别提高时调整。
- 纯文档、测试、格式化或 CI 维护不强制升版；如果这些改动同时修复了交付功能，仍按修复处理。用 `fix:` / `feat:`（可加 scope）标记对应提交和 PR，破坏性变更用 `!:` 或 `BREAKING CHANGE:`，供 CI 检查；分类本身由开发者和审阅者负责。
- CI 根据目标分支历史中可达的最近正式版本标签，汇总未发布变更并检查最低升版幅度，同时不允许低于目标分支已有的候选版本。用 `bash scripts/sync-version.sh X.Y.Z` 同步 UPM、Editor Bridge、Python CLI 和锁文件，并将同批变更归入 [变更日志](./packages/com.mk.unity-agent-bridge/CHANGELOG.md) 的同一版本小节。在本地验证后把版本改动和对应修改一起提交。
- **升版不等于发布。** `sync-version.sh` 不提交、不打标签、不推送；推送分支也不授权打标签或发布。已升好版本的候选不要再用会递增版本并打标签的 `bump-version.sh`；见 [发布流程](./README.md#发布流程)。

This file is the entry point for AI coding assistants. For detailed behavior rules, see [AGENTS_RULE.md](./AGENTS_RULE.md).
