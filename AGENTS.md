# AGENTS.md

本文件为 AI 辅助开发工具的入口配置，具体的行为规则请参阅 [AGENTS_RULE.md](./AGENTS_RULE.md)。

开始开发前，请先读 [Agent 开发交接](./docs/agent-handoff.md)，确认当前范围、代码入口、回归命令和后续优先级。旧计划仅用于回查设计，不作为当前任务清单。

## 版本规则（CLI 与 Unity UPM 同步）

- 修复 Bug 用 **Patch**：`X.Y.Z → X.Y.(Z+1)`，即使只有一行也要升。向后兼容的新功能用 **Minor**：`X.Y.Z → X.(Y+1).0`；同一交付同时含新功能和修复时按 Minor，不叠加 Patch。破坏性变更单独确认 Major。
- 纯文档、测试、格式化或 CI 维护不强制升版；如果这些改动同时修复了交付功能，仍按修复处理。用 `fix:` / `feat:`（可加 scope）标记对应提交和 PR，破坏性变更用 `!:` 或 `BREAKING CHANGE:`，供 CI 检查；分类本身由开发者和审阅者负责。
- 基于工作开始时的基线版本选定目标，用 `bash scripts/sync-version.sh X.Y.Z` 同步 UPM、Editor Bridge、Python CLI 和锁文件，并更新 [变更日志](./packages/com.mk.unity-agent-bridge/CHANGELOG.md)。在本地验证后把版本改动和对应修改一起提交。
- **升版不等于发布。** `sync-version.sh` 不提交、不打标签、不推送；推送分支也不授权打标签或发布。已升好版本的候选不要再用会递增版本并打标签的 `bump-version.sh`；见 [发布流程](./README.md#发布流程)。

This file is the entry point for AI coding assistants. For detailed behavior rules, see [AGENTS_RULE.md](./AGENTS_RULE.md).
