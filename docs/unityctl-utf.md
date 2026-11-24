# unityctl：Unity 2022.3 测试入口

`unityctl test run` 使用项目安装的 Unity Test Framework，在独立 Unity Editor batchmode 进程中运行 EditMode 或 PlayMode。不需要正在联网的 Bridge，也不自动安装 UTF、关闭 Editor 或更改项目配置。运行前关闭**该项目**的 Editor，或使用独立测试副本。PlayMode 指在 Editor 中运行，不是 Player 真机测试，也不是 Game View 视觉测试。

```bash
unityctl --project /path/to/project test run --mode EditMode --job-id unit-01
unityctl --project /path/to/project test run --mode PlayMode --filter 'Game.Tests.Login' --timeout 600
```

如未在项目本机配置中指定 Unity，可传 `--unity /path/to/Unity.app`。默认超时 900 秒。过滤表达式遵循 [Unity UTF CLI](https://docs.unity3d.com/Packages/com.unity.test-framework@1.1/manual/reference-command-line.html)，不传则由 Unity 执行该模式的全部测试。

## 查询与 CI

运行命令在前台等待结果；需要非阻塞编排时，把命令交给 Harness 的后台执行能力，预先设一个**未用过**的 `--job-id`，然后在另一进程查询：

```bash
unityctl --project /path/to/project test status unit-01
```

运行过程和最终结果位于项目的 `.unity-agent/test-runs/<job-id>/`：

- `test-report.json`：状态、退出码、计数、失败测试或套件、消息及堆栈；Unity 没有产出有效 XML 时，计数不会被伪造。
- `results.xml`：Unity 原始 NUnit 结果，如已生成。
- `unity.log`：Unity 日志，编译失败或无 XML 时优先检查。

`test run` 通过时退出码为 0，测试失败、全跳过/未匹配、无法判定、结果缺失或超时时非零退出。`test status` 的 `ok: true` 也可能表示任务仍在运行；自动化验收只认 `status: "passed"`。若编排进程异常退出且没有最终报告，查询会返回 `interrupted`。

产物可能包含路径和测试数据。新初始化的项目会忽略 `test-runs/`；现有项目可将该目录加入 `.unity-agent/.gitignore`。CI 可归档这三份文件，但应先检查内容是否适合公开。
