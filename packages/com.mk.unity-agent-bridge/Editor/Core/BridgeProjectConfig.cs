using System;
using System.IO;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor
{
    /// <summary>
    /// 只读取 .unity-agent/config.json 中的 bridge.preferredPort。配置文件是纯 JSON，
    /// 不再支持注释；host 恒为 127.0.0.1，不可配置。
    /// </summary>
    public static class BridgeProjectConfig
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
            if (payload == null)
            {
                return Settings.Default();
            }

            int preferredPort = payload.bridge != null
                && payload.bridge.preferredPort >= 1
                && payload.bridge.preferredPort <= 65535
                ? payload.bridge.preferredPort
                : DefaultPreferredPort;

            CaptureScreenshotPayload screenshotPayload = payload.capture?.screenshot ?? new CaptureScreenshotPayload();
            GameplayPayload gameplayPayload = payload.gameplay ?? new GameplayPayload();
            return new Settings
            {
                preferredPort = preferredPort,
                ScreenshotCapture = new CaptureScreenshotSettings
                {
                    Enabled = screenshotPayload.enabled,
                    AllowAgentRequest = screenshotPayload.allowAgentRequest,
                    OnAssertFailure = screenshotPayload.onAssertFailure,
                    OnScenarioStep = screenshotPayload.onScenarioStep,
                    MaxPerSession = screenshotPayload.maxPerSession,
                    MaxLongEdge = screenshotPayload.maxLongEdge,
                    AgentImageAccess = screenshotPayload.agentImageAccess
                },
                Gameplay = new GameplaySettings
                {
                    Enabled = gameplayPayload.enabled,
                    Whitelist = gameplayPayload.whitelist ?? Array.Empty<string>()
                }
            };
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
            public CapturePayload capture;
            public GameplayPayload gameplay;
        }

        [Serializable]
        private sealed class BridgePayload
        {
            public int preferredPort;
        }

        [Serializable]
        private sealed class CapturePayload
        {
            public CaptureScreenshotPayload screenshot;
        }

        /// <summary>
        /// 字段初始值 = 1.3 规定的缺省值；JsonUtility.FromJson&lt;T&gt;() 对 JSON 里缺失的字段
        /// 保留这些初始值（等价于先 new 一个默认实例再做 overwrite），因此 config.json 完全不写
        /// "capture" 段或只写部分字段都能拿到正确的缺省语义。
        /// </summary>
        [Serializable]
        private sealed class CaptureScreenshotPayload
        {
            public bool enabled = true;
            public bool allowAgentRequest = true;
            public bool onAssertFailure = true;
            public bool onScenarioStep = true;
            public int maxPerSession = 50;
            public int maxLongEdge = 1280;
            public string agentImageAccess = "allow";
        }

        /// <summary>
        /// gameplay command bridge 是任意代码执行入口，enabled 默认 false（安全默认）；
        /// 未写 "gameplay" 段或省略 whitelist 时视为关闭 + 空白名单。
        /// </summary>
        [Serializable]
        private sealed class GameplayPayload
        {
            public bool enabled = false;
            public string[] whitelist = Array.Empty<string>();
        }

        public sealed class GameplaySettings
        {
            public bool Enabled;
            public string[] Whitelist;

            public static GameplaySettings Default()
            {
                return new GameplaySettings { Enabled = false, Whitelist = Array.Empty<string>() };
            }
        }

        public sealed class CaptureScreenshotSettings
        {
            public bool Enabled;
            public bool AllowAgentRequest;
            public bool OnAssertFailure;
            public bool OnScenarioStep;
            public int MaxPerSession;
            public int MaxLongEdge;
            public string AgentImageAccess;

            public static CaptureScreenshotSettings Default()
            {
                return new CaptureScreenshotSettings
                {
                    Enabled = true,
                    AllowAgentRequest = true,
                    OnAssertFailure = true,
                    OnScenarioStep = true,
                    MaxPerSession = 50,
                    MaxLongEdge = 1280,
                    AgentImageAccess = "allow"
                };
            }
        }

        public sealed class Settings
        {
            public int preferredPort;
            public CaptureScreenshotSettings ScreenshotCapture = CaptureScreenshotSettings.Default();
            public GameplaySettings Gameplay = GameplaySettings.Default();

            public static Settings Default()
            {
                return new Settings { preferredPort = DefaultPreferredPort };
            }
        }
    }
}
