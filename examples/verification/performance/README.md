# 同一场景的 Editor 性能回归

这个示例固定一关、固定输入（无输入），先预热，再采样 Unity Editor Play Mode 的主线程计数器和每帧 GC 分配。它帮你发现同机相对退化，不能证明 Player 包、真机 GPU 或目标 FPS 达标。

## 一次性接入

1. 在开发/测试 Unity 项目安装与 CLI 配套的 Bridge，把 [PerformanceFrameProbe.cs](PerformanceFrameProbe.cs) 放进该项目的 `Assets/`。它不需要挂载组件、不依赖 UGUI，只提供标记当前游戏帧和读取经过帧数的两个方法。
2. 将 [baseline.json](baseline.json) 的首个场景路径改为要重复测量的场景（默认占位 `Assets/Scenes/Performance.unity`）。选定相同机器、Unity 版本、画质、Game View 尺寸、目标帧率/VSync 和进程条件；使用固定的场景数据与种子。用真实输入验证时，同一次实验的前后版本使用同一录制/操作序列。
3. 将下列 `gameplay` 设置合并到测试项目的 `.unity-agent/config.json`（不覆盖其他配置，不在生产环境开启）：

```json
{
  "gameplay": {
    "enabled": true,
    "whitelist": [
      "UnityRunBridge.Examples.PerformanceFrameProbe.Mark",
      "UnityRunBridge.Examples.PerformanceFrameProbe.FramesSinceMark"
    ]
  }
}
```

## 建立基线，再设置预算

将测试脚本保存为 `performance-baseline.json`，在同一机器打开带图形的 Editor，按顺序运行，不并行：

```bash
unityctl refresh
unityctl scenario validate performance-baseline.json
unityctl scenario run performance-baseline.json --session perf-base-1
unityctl scenario run performance-baseline.json --session perf-base-2
unityctl scenario run performance-baseline.json --session perf-base-3
```

- 每次运行前用 `unityctl status` 确认 Bridge 已恢复、Editor 已回到 idle。刚退出 Play Mode 时可能正在重新加载程序集；如果下一轮还未启动就遇到连接错误，等恢复后再运行，不把失败会话算入基线。
- 示例至少等待 120 个游戏帧预热，随后经过至少 240 个游戏帧再停采样；轮询可能多等若干帧。这不是逐帧暂停机制。样本以 Editor update 读取；若前后采样量或场景负载明显不同，重跑，不直接比较。
- 每个指标至少需要 180 条有效样本。基线里的 CPU `greaterThan: 0` 和 GC `atLeast: 0` **只是采样有效性门槛，不是性能目标**。尤其不要用零主线程耗时当作可用基线。根据三轮有效结果（各断言 `actual`）和可解释的噪声余量分别设置预算，例如最大基线 p95 加 10% 主线程余量，以及另定非零的 GC 分配容忍值。不要用设备 FPS 预算直接代替 Editor 主线程预算。
- 保存为 `performance-budget.json`：只把两个指标的基线比较符替换为各自的 `atMost` 数值，不改场景与采样窗口。改动后执行 `unityctl scenario run performance-budget.json --session perf-after-1`，在相同条件下重复三轮，用同一阈值比较。

## 判读证据

从 `sessionPath` 中取 `artifacts/metrics.jsonl`、`artifacts/scenario-result.json` 和 `summary.json`。保存机器、画质、场景、运行模式、样本数和两项 p95 的前后结果；不要将 Editor 的主线程指标当成整帧或 GPU 耗时。

- `metric_not_available`：无该计数器数据，不是 0；检查 `profile-start` 步骤的 `unavailableMetrics`、Unity 版本和渲染管线。
- `metric_insufficient_samples`：样本未达到下限；排查暂停、短窗口和写盘问题。
- `profile_interrupted`：中断前数据可能保留作为排障素材，本轮预算无效。恢复后重跑；不要将部分采样并入基线。
- 若怀疑 GPU、渲染线程或真机瓶颈，在目标设备、相同画质和场景用 Player + Profiler 复测。不要混合 headless、GUI Editor 与 Player 的基线。
