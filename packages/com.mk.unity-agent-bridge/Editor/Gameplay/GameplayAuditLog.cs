using System;
using System.IO;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Gameplay
{
    /// <summary>
    /// invoke 是任意代码执行入口，每次调用都要落盘可审计：追加一行到当前 session 的
    /// artifacts/gameplay-invokes.jsonl（无 session 时写 scratch/），与项目
    /// 「事实落盘可审计」模型一致。这是同一份持续追加的文件，不走 ArtifactPathGuard 的
    /// 递增序号命名（那是给"每次一份新文件"的产物，如截图用的）。
    /// </summary>
    internal static class GameplayAuditLog
    {
        private const string FileName = "gameplay-invokes.jsonl";

        public static void Append(string command, JsonValue args, JsonValue resultSummary, long durationMs, string reason)
        {
            try
            {
                string directory = ArtifactPathGuard.ResolveArtifactDirectory();
                string path = Path.Combine(directory, FileName);

                JsonValue line = JsonValue.NewObject();
                line["time"] = DateTime.UtcNow.ToString("O");
                line["command"] = command;
                line["args"] = args ?? JsonValue.NewObject();
                line["result"] = resultSummary ?? JsonValue.Null;
                line["durationMs"] = durationMs;
                line["reason"] = string.IsNullOrEmpty(reason) ? "agent" : reason;

                File.AppendAllText(path, line.ToString() + "\n");
            }
            catch (Exception ex)
            {
                // 审计写盘失败不应影响 invoke 的成功/失败判定，只记一条警告方便排查。
                Debug.LogWarning($"Unity Agent Bridge: 写入 gameplay-invokes.jsonl 失败：{ex.Message}");
            }
        }
    }
}
