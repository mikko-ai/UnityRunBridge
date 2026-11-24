# 第三方来源

`unityctl/asset_audit.py` 根据 awesome-gamedev-agent-skills 的离线项目检查
（`skills/unity/unity-csharp-scripting/scripts/check_unity_project.py`，本地参考版本
`c6ca6c4`）适配。保留上游 Apache-2.0 LICENSE 与 NOTICE。改动包括移除独立
CLI 和类名/推断移动规则、限制缓存与链接扫描范围、显式报告部分覆盖，并接入
`unityctl health` 的结果与退出码。

`unityctl/build_size.py` 和 `unityctl/build_size_scan.py` 分别根据同一版本的
`skills/unity/unity-build-size/scripts/build_report.py` 和
`skills/unity/unity-build-size/scripts/check_unity_build_size.py` 适配。
改动包括使用 unityctl JSON 接口、区分日志/摘要/交付产物、截断日志不回退到旧构建、
限定静态扫描范围和读取量、不生成修改命令，以及对未知覆盖显式提示。
