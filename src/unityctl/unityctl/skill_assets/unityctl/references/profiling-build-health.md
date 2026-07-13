# unityctl reference：性能 / 构建 / 健康检查

适用场景：性能采样（profile）、Player 构建诊断（build）、项目健康检查（health）。命令输出均为 JSON 信封（成功 `{"ok": true, ...}`，失败 stderr `{"ok": false, "code", "message"}`）。

**Capability**：`profiling` 与 `health` 属于 Core 能力，**不依赖** UGUI。`build` 走独立 batchmode 进程，也不经过 Bridge capability 门控。

## 性能采样（ProfilerRecorder，需 Play Mode）

`unityctl profile` 用 `ProfilerRecorder` 逐帧采样一组固定计数器（v1 不支持自定义配置），写出 `metrics.jsonl`，用来在改动前后做相对回归比较。

```bash
unityctl profile start                              # 不指定目录时落到当前 session 的 artifacts/，无 session 落 .unity-agent/scratch/
unityctl profile start --latest                     # 显式落到最近 session 的 artifacts/
# 让游戏运行一段时间……
unityctl profile status                             # 查看是否在采样、已采样多少帧
unityctl profile stop                                # 停止采样，返回 metricsPath / frameCount / interrupted / aggregates（avg/max/p95）
```

- 固定计数器集（`metrics.jsonl` 字段名 → `ProfilerRecorder` 计数器）：`frameTimeMs`（Internal/"CPU Main Thread Frame Time"，纳秒转毫秒）、`gcAllocBytes`（Memory/"GC Allocated In Frame"）、`drawCalls`（Render/"Draw Calls Count"）、`setPassCalls`（Render/"SetPass Calls Count"）、`triangles`（Render/"Triangles Count"）、`totalMemoryBytes`（Memory/"Total Used Memory"）、`gcMemoryBytes`（Memory/"GC Used Memory"）。
- 计数器在当前 Unity 版本/渲染管线下缺失时不采样该项，记入 `profile start` 响应的 `unavailableMetrics` 列表（不静默返回 0）；scenario 的 `metric` 断言引用不可用指标会判 `metric_not_available`。
- 每 60 帧批量落盘一次（避免逐帧 IO）；domain reload / 退出 Play Mode 会打断采样，已落盘的批次保留，未落盘的一批（< 60 帧）按设计丢弃，`status`/`stop` 会如实返回 `interrupted: true`。
- **重要限制**：Editor 内采样含 Editor 自身开销，绝对值不代表真机性能；正确用途是同机同项目改动前后的相对回归比较，阈值应基于本机基线自行设定。
- session 存在 `artifacts/metrics.jsonl` 时，`unityctl summary` 会自动附加 `metrics` 段（各指标 `avg`/`max`/`p95` + `frameCount`）。

## 构建（独立进程，不经过 Bridge）

`unityctl build` spawn 一个新的 batchmode Unity 进程执行 Player 构建，与正在运行、供交互调试的 Editor 实例完全独立——两者不能同时持有同一个项目（Unity 一次只能有一个进程占用 `Library`/`Temp`），所以构建前会检测 `Temp/UnityLockfile` 是否被占用，占用时直接报错，**不会自动关闭已打开的 Editor**。

```bash
unityctl build                                    # 用项目当前 active build target（省略 -buildTarget）
unityctl build --target StandaloneOSX             # 显式指定 Unity 原生 BuildTarget 名
unityctl build --target Android --output /tmp/out.apk --timeout 1800
```

- 目标平台直接透传 Unity 原生 `-buildTarget <target>`（不是自定义参数），保证脚本编译符号（`UNITY_ANDROID` 等）与目标平台一致；缺省时省略该参数，使用项目当前 active build target。
- 产物落在 `.unity-agent/builds/<buildId>/`（`buildId` = 时间戳 + target），含 `build-report.json`（结构见 `schemas/build-report.schema.json`：`result`/`durationMs`/`outputPath`/`sizeBytes`/`errors`/`warnings`/`steps`）与完整的 `build.log`。
- v1 只做 Player 构建（不含 AssetBundle/Addressables）。
- 报告缺失时（多半是脚本编译错误导致 Unity 在真正开始构建前就中止，`-executeMethod` 从未跑起来）会从 `build.log` 里兜底解析 `Foo.cs(12,34): error CSxxxx: ...` 形式的编译错误行，此时 `reportSource` 为 `log_fallback`（正常情况下是 `build_report`）。
- 退出码：`result: "Succeeded"` 为 `0`，其余（`Failed`/`Cancelled`）为 `1`，CI 友好；超时（默认 3600s，`config.json` 的 `timeouts.buildSeconds` 可配，或 `--timeout` 单次覆盖）会杀掉构建进程并报 `build_timeout`。

## 项目健康检查（unityctl health）

`unityctl doctor` 回答「环境能不能跑」（Bridge 连通性、UPM 包、进程占用）；`unityctl health` 回答「项目干不干净」（编译、缺失脚本引用、构建场景列表、包一致性）。四个检查项彼此独立，默认全跑，可用 `--check` 只跑指定项：

```bash
unityctl health                                          # 跑全部四项
unityctl health --check compilation,missing_scripts      # 只跑指定项（逗号分隔）
```

- 四个检查项：
  - `compilation`：触发 `refresh` 并等编译完成，编译失败判 `fail`。
  - `missing_scripts`：分两部分——已加载场景（复用 `hierarchy find --missing-script`）+ 项目内**全部** Prefab 资产（异步 job，按 50 个/tick 批处理避免卡主线程，资产数量大也不会卡住 Editor）；命中任一判 `fail`。
  - `build_scenes`：`EditorBuildSettings.scenes` 里指向不存在文件的条目判 `fail`；项目里存在但未加入该列表的 `.unity` 文件判 `warn`（仅提示，不算错误）。
  - `packages`：`Packages/manifest.json` 与 `packages-lock.json` 依赖不一致，或 `ProjectSettings/ProjectVersion.txt` 记录的 Unity 版本与 `config.json` 的 `unityVersion` 不一致，判 `warn`。Core-only 项目未声明 UGUI 是预期行为，不会因此判 fail。
- 每项检查独立输出 `{ "name", "status": "pass|warn|fail|skipped", "details": [...] }`；`compilation`/`missing_scripts` 需要 Bridge，Bridge 不可达时该项标记 `skipped` 并在 `details` 里说明原因，**不计入整体失败**（`build_scenes`/`packages` 是纯静态检查，任何时候都能跑，不需要先 `unityctl start`）。
- 整体 `status` 取所有检查项里最差的一个（`fail` > `warn` > `pass`，`skipped` 不参与比较）；退出码：`pass`/`warn` 为 `0`，`fail` 为 `1`，CI 门禁友好。
