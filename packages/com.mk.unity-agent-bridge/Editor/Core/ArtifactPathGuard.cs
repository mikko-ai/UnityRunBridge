using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor
{
    /// <summary>
    /// 统一的产物目录约定与路径校验：所有写盘端点（截图/录制/profiling/健康检查）都必须
    /// 经它解析"该写到哪个目录"、校验"目标路径是否合法"，避免各自实现出现口径不一致。
    ///
    /// 约定（见 Phase 0.3）：
    /// - 有活动 session：写 <ProjectRoot>/.unity-agent/sessions/&lt;sessionId&gt;/artifacts/。
    /// - 无 session：写 <ProjectRoot>/.unity-agent/scratch/（供 agent 随手查看，不参与 summary）。
    /// - 命名：&lt;prefix&gt;-&lt;seq&gt;&lt;extension&gt;；seq 从 1 递增；
    ///   session 内持久于 SessionState（跨 domain reload 单调递增），
    ///   scratch 内没有稳定 key，退化为扫描目录同前缀文件数推算。
    /// </summary>
    public static class ArtifactPathGuard
    {
        public const string AgentDirName = ".unity-agent";
        public const string SessionsDirName = "sessions";
        public const string ScratchDirName = "scratch";
        public const string BuildsDirName = "builds";
        public const string ArtifactsSubDirName = "artifacts";

        public static string GetProjectRoot()
        {
            DirectoryInfo assetsDirectory = new DirectoryInfo(Application.dataPath);
            return assetsDirectory.Parent == null ? string.Empty : assetsDirectory.Parent.FullName;
        }

        public static string GetSessionsRoot(string projectRoot) =>
            Path.Combine(projectRoot, AgentDirName, SessionsDirName);

        public static string GetScratchRoot(string projectRoot) =>
            Path.Combine(projectRoot, AgentDirName, ScratchDirName);

        public static string GetBuildsRoot(string projectRoot) =>
            Path.Combine(projectRoot, AgentDirName, BuildsDirName);

        public static bool IsAllowedSessionPath(string projectRoot, string candidatePath) =>
            IsUnder(projectRoot, candidatePath, GetSessionsRoot);

        public static bool IsAllowedScratchPath(string projectRoot, string candidatePath) =>
            IsUnder(projectRoot, candidatePath, GetScratchRoot);

        public static bool IsAllowedBuildsPath(string projectRoot, string candidatePath) =>
            IsUnder(projectRoot, candidatePath, GetBuildsRoot);

        /// <summary>写盘端点（截图/录制/profiling/健康检查）的通用校验：必须位于 sessions/ 或 scratch/ 之下。</summary>
        public static bool IsAllowedArtifactPath(string projectRoot, string candidatePath)
        {
            return IsAllowedSessionPath(projectRoot, candidatePath) || IsAllowedScratchPath(projectRoot, candidatePath);
        }

        /// <summary>
        /// 解析"现在应该写到哪个目录"：有活动 session 时是它的 artifacts/ 子目录（自动创建），
        /// 否则退化为 scratch/（自动创建）。
        /// </summary>
        public static string ResolveArtifactDirectory()
        {
            string directory;
            if (SessionService.HasActiveSession && !string.IsNullOrEmpty(SessionService.CurrentSessionPath))
            {
                directory = Path.Combine(SessionService.CurrentSessionPath, ArtifactsSubDirName);
            }
            else
            {
                directory = GetScratchRoot(GetProjectRoot());
            }

            Directory.CreateDirectory(directory);
            return directory;
        }

        /// <summary>
        /// 生成 "&lt;prefix&gt;-&lt;seq&gt;&lt;extension&gt;" 形式的下一个产物路径（seq 从 1 开始）。
        /// </summary>
        public static string NextSequencedPath(string directory, string prefix, string extension)
        {
            int seq = SessionService.HasActiveSession
                ? NextSequenceForSession(prefix)
                : NextSequenceForDirectory(directory, prefix, extension);
            return Path.Combine(directory, $"{prefix}-{seq}{extension}");
        }

        private static int NextSequenceForSession(string prefix)
        {
            string key = $"Mk.UnityAgentBridge.ArtifactSeq.{SessionService.CurrentSessionId}.{prefix}";
            int next = SessionState.GetInt(key, 0) + 1;
            SessionState.SetInt(key, next);
            return next;
        }

        internal static int NextSequenceForDirectory(string directory, string prefix, string extension)
        {
            if (!Directory.Exists(directory))
            {
                return 1;
            }

            int max = 0;
            string searchPattern = $"{prefix}-*{extension}";
            foreach (string file in Directory.GetFiles(directory, searchPattern))
            {
                string name = Path.GetFileNameWithoutExtension(file);
                string numberPart = name.Length > prefix.Length + 1 ? name.Substring(prefix.Length + 1) : string.Empty;
                if (int.TryParse(numberPart, out int number) && number > max)
                {
                    max = number;
                }
            }

            return max + 1;
        }

        private static bool IsUnder(string projectRoot, string candidatePath, Func<string, string> rootResolver)
        {
            if (string.IsNullOrWhiteSpace(projectRoot) || string.IsNullOrWhiteSpace(candidatePath))
            {
                return false;
            }

            string projectFullPath = Path.GetFullPath(projectRoot);
            string allowedRoot = Normalize(Path.GetFullPath(rootResolver(projectFullPath)));
            string fullCandidate = Normalize(Path.GetFullPath(candidatePath));
            return fullCandidate.StartsWith(allowedRoot + "/", StringComparison.Ordinal);
        }

        internal static string Normalize(string path) => path.Replace('\\', '/').TrimEnd('/');
    }
}
