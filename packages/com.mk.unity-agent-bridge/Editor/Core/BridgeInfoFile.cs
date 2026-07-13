using System;
using System.Diagnostics;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor
{
    /// <summary>
    /// 负责维护 .unity-agent/bridge.json 握手文件：CLI 通过它发现 Bridge 实际监听的端口、
    /// 鉴权 token 与进程信息，而不依赖静态配置的端口号。
    /// Phase 2 从旧单体下沉到 Core：Host（composition root）与鉴权 pipeline 都要用它，
    /// 而 Host 只引用 Core，因此握手文件逻辑必须归属 Core。
    /// </summary>
    public static class BridgeInfoFile
    {
        private const string TokenKey = "Mk.UnityAgentBridge.Token";

        public static string GetOrCreateToken()
        {
            string token = SessionState.GetString(TokenKey, string.Empty);
            if (string.IsNullOrEmpty(token))
            {
                token = Guid.NewGuid().ToString("N");
                SessionState.SetString(TokenKey, token);
            }

            return token;
        }

        public static string GetPath()
        {
            return Path.Combine(GetProjectRoot(), ".unity-agent", "bridge.json");
        }

        /// <summary>
        /// 原子写入 bridge.json：先写临时文件，再替换目标文件，避免 CLI 读到写了一半的内容。
        /// 绑定成功后立即调用一次；每次 domain reload 后 server 重新绑定成功也要覆盖写。
        /// </summary>
        public static void Write(int port, string token)
        {
            string path = GetPath();
            Directory.CreateDirectory(Path.GetDirectoryName(path));

            BridgeInfoPayload payload = new BridgeInfoPayload
            {
                schemaVersion = 1,
                port = port,
                pid = Process.GetCurrentProcess().Id,
                token = token,
                unityVersion = Application.unityVersion,
                projectPath = GetProjectRoot(),
                startedAt = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
            };

            string json = JsonUtility.ToJson(payload, true);
            string tmpPath = path + ".tmp";
            File.WriteAllText(tmpPath, json);

            if (File.Exists(path))
            {
                File.Delete(path);
            }

            File.Move(tmpPath, path);
        }

        /// <summary>
        /// 仅在 Editor 真正退出时调用；domain reload（进入/退出 Play Mode 触发）时绝对不能删除，
        /// 否则 CLI 会在 reload 窗口里误判 Editor 已经退出。
        /// </summary>
        public static void Delete()
        {
            string path = GetPath();
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }

        private static string GetProjectRoot()
        {
            DirectoryInfo assetsDirectory = new DirectoryInfo(Application.dataPath);
            return assetsDirectory.Parent == null ? string.Empty : assetsDirectory.Parent.FullName;
        }

        [Serializable]
        private sealed class BridgeInfoPayload
        {
            public int schemaVersion;
            public int port;
            public int pid;
            public string token;
            public string unityVersion;
            public string projectPath;
            public string startedAt;
        }
    }
}
