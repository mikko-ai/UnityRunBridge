namespace Mk.UnityAgentBridge.Editor
{
    public static class BridgeConfig
    {
        public const string Version = "0.3.0";

        /// <summary>
        /// 监听地址硬编码为 127.0.0.1，不开放为配置项：暴露到局域网需要完整的安全设计，
        /// 不是改一个配置字段就能安全打开的能力。
        /// </summary>
        public const string Host = "127.0.0.1";

        public static int PreferredPort => BridgeProjectConfig.Load().preferredPort;

        public static string BuildPrefix(int port)
        {
            return $"http://{Host}:{port}/";
        }
    }
}
