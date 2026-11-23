# 第三方来源

`unityctl/asset_audit.py` 根据 awesome-gamedev-agent-skills 的离线项目检查
（`skills/unity/unity-csharp-scripting/scripts/check_unity_project.py`，本地参考版本
`c6ca6c4`）适配。保留上游 Apache-2.0 LICENSE 与 NOTICE。改动包括移除独立
CLI 和类名/推断移动规则、限制缓存与链接扫描范围、显式报告部分覆盖，并接入
`unityctl health` 的结果与退出码。
