using System;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using UnityEngine;

namespace Elex.UnityAgentBridge.Editor
{
    internal static class BridgeProjectConfig
    {
        public const string DefaultHost = "127.0.0.1";
        public const int DefaultPort = 17890;

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

            string cleanJson = StripTrailingCommas(StripComments(json));
            ConfigPayload payload = JsonUtility.FromJson<ConfigPayload>(cleanJson);
            if (payload == null || payload.bridge == null)
            {
                return Settings.Default();
            }

            string host = string.IsNullOrWhiteSpace(payload.bridge.host)
                ? DefaultHost
                : payload.bridge.host;
            int port = payload.bridge.port <= 0 ? DefaultPort : payload.bridge.port;
            return new Settings { host = host, port = port };
        }

        public static string BuildPrefix(string host, int port)
        {
            return $"http://{host}:{port}/";
        }

        public static string GetConfigPath()
        {
            DirectoryInfo assetsDirectory = new DirectoryInfo(Application.dataPath);
            string projectRoot = assetsDirectory.Parent == null
                ? string.Empty
                : assetsDirectory.Parent.FullName;
            return Path.Combine(projectRoot, ".unity-agent", "config.jsonc");
        }

        private static string StripComments(string text)
        {
            StringBuilder builder = new StringBuilder();
            bool inString = false;
            bool escape = false;

            for (int i = 0; i < text.Length; i++)
            {
                char current = text[i];
                char next = i + 1 < text.Length ? text[i + 1] : '\0';

                if (inString)
                {
                    builder.Append(current);
                    if (escape)
                    {
                        escape = false;
                    }
                    else if (current == '\\')
                    {
                        escape = true;
                    }
                    else if (current == '"')
                    {
                        inString = false;
                    }
                    continue;
                }

                if (current == '"')
                {
                    inString = true;
                    builder.Append(current);
                    continue;
                }

                if (current == '/' && next == '/')
                {
                    i += 2;
                    while (i < text.Length && text[i] != '\n' && text[i] != '\r')
                    {
                        i++;
                    }
                    i--;
                    continue;
                }

                if (current == '/' && next == '*')
                {
                    i += 2;
                    while (i + 1 < text.Length && !(text[i] == '*' && text[i + 1] == '/'))
                    {
                        i++;
                    }
                    i++;
                    continue;
                }

                builder.Append(current);
            }

            return builder.ToString();
        }

        private static string StripTrailingCommas(string text)
        {
            return Regex.Replace(text, @",\s*([}\]])", "$1");
        }

        [Serializable]
        private sealed class ConfigPayload
        {
            public BridgePayload bridge;
        }

        [Serializable]
        private sealed class BridgePayload
        {
            public string host;
            public int port;
        }

        [Serializable]
        public sealed class Settings
        {
            public string host;
            public int port;

            public static Settings Default()
            {
                return new Settings { host = DefaultHost, port = DefaultPort };
            }
        }
    }
}
