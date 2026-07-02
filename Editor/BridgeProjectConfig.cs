using System;
using System.IO;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor
{
    /// <summary>
    /// 只读取 .unity-agent/config.json 中的 bridge.preferredPort。配置文件是纯 JSON，
    /// 不再支持注释；host 恒为 127.0.0.1，不可配置。
    /// </summary>
    internal static class BridgeProjectConfig
    {
        public const int DefaultPreferredPort = 17890;

        public static Settings Load()
        {
            string path = GetConfigPath();
            if (!File.Exists(path))
            {
                return Settings.Default();
            }

            return FromJson(File.ReadAllText(path));
        }

        public static Settings FromJson(string json)
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                return Settings.Default();
            }

            ConfigPayload payload = JsonUtility.FromJson<ConfigPayload>(json);
            if (payload == null
                || payload.bridge == null
                || payload.bridge.preferredPort < 1
                || payload.bridge.preferredPort > 65535)
            {
                return Settings.Default();
            }

            return new Settings { preferredPort = payload.bridge.preferredPort };
        }

        public static string GetConfigPath()
        {
            DirectoryInfo assetsDirectory = new DirectoryInfo(Application.dataPath);
            string projectRoot = assetsDirectory.Parent == null
                ? string.Empty
                : assetsDirectory.Parent.FullName;
            return Path.Combine(projectRoot, ".unity-agent", "config.json");
        }

        [Serializable]
        private sealed class ConfigPayload
        {
            public BridgePayload bridge;
        }

        [Serializable]
        private sealed class BridgePayload
        {
            public int preferredPort;
        }

        [Serializable]
        public sealed class Settings
        {
            public int preferredPort;

            public static Settings Default()
            {
                return new Settings { preferredPort = DefaultPreferredPort };
            }
        }
    }
}
