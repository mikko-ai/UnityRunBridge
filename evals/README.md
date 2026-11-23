# 内置 Skill 触发评测

这里评测的是**收到请求后该选哪份 Skill**，不是 Unity 命令执行质量，也不是所有 Agent 宿主的实际触发率。不新增 Router，不运行 Unity，也不自动调用模型或第三方服务。

语料按上游 awesome-gamedev-agent-skills 的分类思路，为 UnityRunBridge 重新编写中英双语样本：

| 类别 | 目的 |
|---|---|
| `should` | 选中一个合适的内置 Skill |
| `near-miss` | 问题用词相近，但排除容易被误选的那个 Skill |
| `combo` | 用户确实同时要执行验证和维护项目 Skill |
| `none` | 仅写代码、普通文案、仅列目录，或仅在自然语言提到一个必须手动调用的 Skill |

`unityctl-project-skill-creator` 带 `disable-model-invocation: true`。套件把明确的 `$unityctl-project-skill-creator` 当作用户手动调用；没有该调用时不把普通创建/更新请求算成自动触发。到支持相应手动调用语法的宿主复测时，以该宿主的实际调用记录为准。

## 本地校验（CI）

```bash
python3 scripts/eval-skill-triggers.py --check
```

检查分发资源的名称、单行 frontmatter、版本值和相对 Markdown 引用，以及语料覆盖、重复及调用授权。Python 回归测试会同时校验源码与用实际安装器复制到临时目录的 Skill。可用 `--assets PATH` 指定干净的已安装 Skill 目录；不要指向混有用户其他 Skill 的目录。

## 独立盲评

```bash
python3 scripts/eval-skill-triggers.py --export > /tmp/urb-trigger-packet.json
# 把上面的 JSON 单独交给要评测的模型或人工评审，用全新的会话，不给答案集或完整 SKILL.md。
# 将返回的 { "zh01": ["unityctl"], ... } 保存到 /tmp/urb-trigger-answers.json。
python3 scripts/eval-skill-triggers.py --score /tmp/urb-trigger-answers.json
```

每道题必须给出已知 Skill 名称集合或空数组。额外选择和漏选都使该题失败；结果包括逐题漏选/误选/不允许的选择、分类通过数、micro precision/recall。退出码：`0` 全通过，`1` 有触发错误，`2` 输入或资产无效。保存模型版本、宿主、请求设置、导出包的指纹和分数。比较两版描述时固定用例和模型，分别导出；修改评测题目或标准应单独记录。

仓库测试里用预设选择验证评测器能判通过、漏选、误选和人工调用边界，这不是模型成绩；不要把评分器自测输出当作触发准确率。
