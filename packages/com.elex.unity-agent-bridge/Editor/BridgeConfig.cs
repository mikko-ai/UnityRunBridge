namespace Elex.UnityAgentBridge.Editor
{
    internal static class BridgeConfig
    {
        public const string Version = "0.1.0";

        public static string Host
        {
            get
            {
                return BridgeProjectConfig.Load().host;
            }
        }

        public static int Port
        {
            get
            {
                return BridgeProjectConfig.Load().port;
            }
        }

        public static string Prefix
        {
            get
            {
                BridgeProjectConfig.Settings settings = BridgeProjectConfig.Load();
                return BridgeProjectConfig.BuildPrefix(settings.host, settings.port);
            }
        }
    }
}
