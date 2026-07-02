using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using UnityEditor;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor
{
    [InitializeOnLoad]
    internal static class BridgeServer
    {
        private const int MaxPortAttempts = 10;

        private static readonly ConcurrentQueue<QueuedRequest> PendingRequests = new ConcurrentQueue<QueuedRequest>();
        private static HttpListener listener;
        private static Thread listenerThread;
        private static bool isRunning;

        static BridgeServer()
        {
            EditorApplication.update += ProcessPendingRequests;
            AssemblyReloadEvents.beforeAssemblyReload += Stop;
            EditorApplication.quitting += StopForEditorQuit;
            SessionController.RestoreActiveSession();
            Start();
        }

        public static void Start()
        {
            if (isRunning)
            {
                return;
            }

            int preferredPort = BridgeProjectConfig.Load().preferredPort;
            string token = BridgeInfoFile.GetOrCreateToken();

            foreach (int candidatePort in BuildCandidatePorts(preferredPort, MaxPortAttempts))
            {
                try
                {
                    listener = new HttpListener();
                    listener.Prefixes.Add(BridgeConfig.BuildPrefix(candidatePort));
                    listener.Start();
                    isRunning = true;

                    listenerThread = new Thread(ListenLoop)
                    {
                        IsBackground = true,
                        Name = "UnityAgentBridgeServer"
                    };
                    listenerThread.Start();

                    BridgeInfoFile.Write(candidatePort, token);

                    Debug.Log($"Unity Agent Bridge listening on {BridgeConfig.BuildPrefix(candidatePort)}");
                    return;
                }
                catch (HttpListenerException)
                {
                    listener?.Close();
                    listener = null;
                    isRunning = false;
                }
            }

            Debug.LogWarning(
                $"Unity Agent Bridge could not bind any port in [{preferredPort}, {preferredPort + MaxPortAttempts - 1}]"
            );
        }

        /// <summary>
        /// 每次 domain reload（beforeAssemblyReload）都会调用，只停监听线程，
        /// 绝不删除 bridge.json——reload 后静态构造函数会重新执行 Start() 覆盖写。
        /// </summary>
        public static void Stop()
        {
            isRunning = false;

            EditorApplication.update -= ProcessPendingRequests;
            AssemblyReloadEvents.beforeAssemblyReload -= Stop;
            EditorApplication.quitting -= StopForEditorQuit;

            if (listener != null)
            {
                listener.Stop();
                listener.Close();
                listener = null;
            }
        }

        private static void StopForEditorQuit()
        {
            SessionController.EndSession();
            BridgeInfoFile.Delete();
            Stop();
        }

        private static void ListenLoop()
        {
            while (isRunning && listener != null && listener.IsListening)
            {
                try
                {
                    HttpListenerContext context = listener.GetContext();
                    HandleContext(context);
                }
                catch (HttpListenerException)
                {
                    isRunning = false;
                }
                catch (ObjectDisposedException)
                {
                    isRunning = false;
                }
            }
        }

        private static void HandleContext(HttpListenerContext context)
        {
            QueuedRequest request = new QueuedRequest(context);
            PendingRequests.Enqueue(request);

            if (!request.Completed.WaitOne(TimeSpan.FromSeconds(30)))
            {
                request.TimedOut = true;
                WriteJson(context.Response, 500, BridgeResponse.Failure("internal_error", "bridge request timed out"));
                return;
            }

            WriteJson(context.Response, request.StatusCode, request.Payload);
        }

        private static void ProcessPendingRequests()
        {
            while (PendingRequests.TryDequeue(out QueuedRequest request))
            {
                if (request.TimedOut)
                {
                    request.Completed.Set();
                    continue;
                }

                try
                {
                    object payload = Route(request.Context.Request);
                    request.StatusCode = ResolveStatusCode(payload as BridgeResponse);
                    request.Payload = payload;
                }
                catch (Exception ex)
                {
                    request.StatusCode = 500;
                    request.Payload = BridgeResponse.Failure("internal_error", ex.Message);
                }
                finally
                {
                    request.Completed.Set();
                }
            }
        }

        private static object Route(HttpListenerRequest request)
        {
            if (!IsAuthorized(request))
            {
                return BridgeResponse.Failure("unauthorized", "missing or invalid X-Bridge-Token header");
            }

            string method = request.HttpMethod.ToUpperInvariant();
            string path = request.Url.AbsolutePath.Trim('/').ToLowerInvariant();

            if (method == "GET" && path == "status")
            {
                return EditorStateProvider.GetStatus();
            }

            if (method == "POST" && path == "play")
            {
                return PlayModeController.EnterPlayMode();
            }

            if (method == "POST" && path == "stop")
            {
                return PlayModeController.ExitPlayMode();
            }

            if (method == "POST" && path == "pause")
            {
                return PlayModeController.Pause();
            }

            if (method == "POST" && path == "resume")
            {
                return PlayModeController.Resume();
            }

            if (method == "POST" && path == "refresh")
            {
                AssetDatabase.Refresh();
                return BridgeResponse.Success("accepted", "asset refresh triggered");
            }

            if (method == "POST" && path == "open-scene")
            {
                OpenSceneRequest sceneRequest = ParseJsonOrNull<OpenSceneRequest>(ReadBody(request));
                if (sceneRequest == null)
                {
                    return BridgeResponse.Failure("invalid_request", "invalid open-scene request body");
                }
                return SceneController.OpenScene(sceneRequest.scenePath);
            }

            if (method == "POST" && path == "session/start")
            {
                SessionStartRequest sessionRequest = ParseJsonOrNull<SessionStartRequest>(ReadBody(request));
                if (sessionRequest == null)
                {
                    return BridgeResponse.Failure("invalid_request", "invalid session start request");
                }
                return SessionController.StartSession(sessionRequest.sessionId, sessionRequest.sessionPath);
            }

            if (method == "POST" && path == "session/end")
            {
                return SessionController.EndSession();
            }

            if (method == "GET" && path == "session/status")
            {
                return SessionController.GetStatus();
            }

            return BridgeResponse.Failure("not_found", $"unsupported route: {method} /{path}");
        }

        private static bool IsAuthorized(HttpListenerRequest request)
        {
            string expectedToken = BridgeInfoFile.GetOrCreateToken();
            string providedToken = request.Headers["X-Bridge-Token"];
            return IsTokenValid(providedToken, expectedToken);
        }

        /// <summary>
        /// 端口顺延候选列表：从 preferredPort 开始连续尝试 maxAttempts 个端口。
        /// 抽成纯函数便于 EditMode 测试覆盖，不依赖 HttpListener。
        /// </summary>
        internal static int[] BuildCandidatePorts(int preferredPort, int maxAttempts)
        {
            int[] ports = new int[maxAttempts];
            for (int i = 0; i < maxAttempts; i++)
            {
                ports[i] = preferredPort + i;
            }

            return ports;
        }

        /// <summary>
        /// JsonUtility.FromJson 对非法 JSON 会抛异常；这里统一转成 null，
        /// 由调用方返回 invalid_request(422) 而不是落入外层的 internal_error(500)。
        /// </summary>
        internal static T ParseJsonOrNull<T>(string json) where T : class
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                return null;
            }

            try
            {
                return JsonUtility.FromJson<T>(json);
            }
            catch (Exception)
            {
                return null;
            }
        }

        /// <summary>
        /// token 校验的纯函数版本，便于 EditMode 测试覆盖缺失/不匹配/匹配三种情况。
        /// </summary>
        internal static bool IsTokenValid(string providedToken, string expectedToken)
        {
            return !string.IsNullOrEmpty(providedToken)
                && !string.IsNullOrEmpty(expectedToken)
                && string.Equals(providedToken, expectedToken, StringComparison.Ordinal);
        }

        private static int ResolveStatusCode(BridgeResponse response)
        {
            if (response == null)
            {
                return 200;
            }

            switch (response.code)
            {
                case "unauthorized":
                    return 401;
                case "not_found":
                    return 404;
                case "busy":
                case "compilation_failed":
                    return 409;
                case "invalid_request":
                    return 422;
                case "internal_error":
                    return 500;
                default:
                    return 200;
            }
        }

        private static string ReadBody(HttpListenerRequest request)
        {
            using StreamReader reader = new StreamReader(request.InputStream, request.ContentEncoding);
            return reader.ReadToEnd();
        }

        private static void WriteJson(HttpListenerResponse response, int statusCode, object payload)
        {
            string json = JsonUtility.ToJson(payload);
            byte[] bytes = Encoding.UTF8.GetBytes(json);
            response.StatusCode = statusCode;
            response.ContentType = "application/json";
            response.ContentEncoding = Encoding.UTF8;
            response.ContentLength64 = bytes.Length;
            response.OutputStream.Write(bytes, 0, bytes.Length);
            response.OutputStream.Close();
        }

        private sealed class QueuedRequest
        {
            public readonly HttpListenerContext Context;
            public readonly ManualResetEvent Completed = new ManualResetEvent(false);
            public volatile bool TimedOut;
            public int StatusCode = 200;
            public object Payload = BridgeResponse.Success("ok", "ok");

            public QueuedRequest(HttpListenerContext context)
            {
                Context = context;
            }
        }
    }
}
