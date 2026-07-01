using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using UnityEditor;
using UnityEngine;

namespace Elex.UnityAgentBridge.Editor
{
    [InitializeOnLoad]
    internal static class BridgeServer
    {
        private static readonly ConcurrentQueue<QueuedRequest> PendingRequests = new ConcurrentQueue<QueuedRequest>();
        private static HttpListener listener;
        private static Thread listenerThread;
        private static bool isRunning;

        static BridgeServer()
        {
            EditorApplication.update += ProcessPendingRequests;
            AssemblyReloadEvents.beforeAssemblyReload += Stop;
            EditorApplication.quitting += Stop;
            Start();
        }

        public static void Start()
        {
            if (isRunning)
            {
                return;
            }

            try
            {
                listener = new HttpListener();
                listener.Prefixes.Add(BridgeConfig.Prefix);
                listener.Start();
                isRunning = true;

                listenerThread = new Thread(ListenLoop)
                {
                    IsBackground = true,
                    Name = "UnityAgentBridgeServer"
                };
                listenerThread.Start();

                Debug.Log($"Unity Agent Bridge listening on {BridgeConfig.Prefix}");
            }
            catch (HttpListenerException ex)
            {
                Debug.LogWarning($"Unity Agent Bridge could not start: {ex.Message}");
                isRunning = false;
            }
        }

        public static void Stop()
        {
            isRunning = false;

            EditorApplication.update -= ProcessPendingRequests;
            AssemblyReloadEvents.beforeAssemblyReload -= Stop;
            EditorApplication.quitting -= Stop;

            if (listener != null)
            {
                listener.Stop();
                listener.Close();
                listener = null;
            }
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
                WriteJson(context.Response, 504, BridgeResponse.Failure("bridge request timed out"));
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
                    request.StatusCode = 200;
                    request.Payload = Route(request.Context.Request);
                }
                catch (Exception ex)
                {
                    request.StatusCode = 500;
                    request.Payload = BridgeResponse.Failure(ex.Message);
                }
                finally
                {
                    request.Completed.Set();
                }
            }
        }

        private static object Route(HttpListenerRequest request)
        {
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

            if (method == "POST" && path == "open-scene")
            {
                string body = ReadBody(request);
                OpenSceneRequest sceneRequest = JsonUtility.FromJson<OpenSceneRequest>(body);
                return SceneController.OpenScene(sceneRequest == null ? string.Empty : sceneRequest.scenePath);
            }

            return BridgeResponse.Failure($"unsupported route: {method} /{path}");
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
            public object Payload = BridgeResponse.Success("ok");

            public QueuedRequest(HttpListenerContext context)
            {
                Context = context;
            }
        }
    }
}
