using System;
using System.Collections.Concurrent;
using System.Net;
using System.Threading;

namespace Mk.UnityAgentBridge.Editor.Host
{
    /// <summary>
    /// 网络承载：HttpListener 绑定、后台接受循环、以及跨线程到主线程的请求队列。
    /// 接受线程只负责入队并阻塞等待；实际路由分发在 <see cref="ProcessPendingRequests"/> 里由主线程
    /// （EditorApplication.update）执行——Unity API 必须在主线程调用。
    /// Phase 2 从旧单体 BridgeServer 拆出到 Host 独立文件；路由函数由 Host 注入以解耦管线。
    /// </summary>
    internal sealed class BridgeHttpHost
    {
        private readonly ConcurrentQueue<QueuedRequest> pendingRequests = new ConcurrentQueue<QueuedRequest>();
        private readonly Func<HttpListenerRequest, object> router;

        private HttpListener listener;
        private Thread listenerThread;
        private volatile bool isRunning;

        public BridgeHttpHost(Func<HttpListenerRequest, object> router)
        {
            this.router = router;
        }

        public bool IsRunning => isRunning;

        /// <summary>尝试绑定单个前缀；成功返回 true 并启动接受线程，被占用返回 false 供调用方顺延端口。</summary>
        public bool TryStart(string prefix)
        {
            try
            {
                listener = new HttpListener();
                listener.Prefixes.Add(prefix);
                listener.Start();
                isRunning = true;

                listenerThread = new Thread(ListenLoop)
                {
                    IsBackground = true,
                    Name = "UnityAgentBridgeServer"
                };
                listenerThread.Start();
                return true;
            }
            catch (HttpListenerException)
            {
                listener?.Close();
                listener = null;
                isRunning = false;
                return false;
            }
        }

        public void Stop()
        {
            isRunning = false;

            if (listener != null)
            {
                listener.Stop();
                listener.Close();
                listener = null;
            }
        }

        public void ProcessPendingRequests()
        {
            while (pendingRequests.TryDequeue(out QueuedRequest request))
            {
                if (request.TimedOut)
                {
                    request.Completed.Set();
                    continue;
                }

                try
                {
                    object payload = router(request.Context.Request);
                    request.StatusCode = ResponseSerializer.ResolveStatusCode(payload);
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

        private void ListenLoop()
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

        private void HandleContext(HttpListenerContext context)
        {
            QueuedRequest request = new QueuedRequest(context);
            pendingRequests.Enqueue(request);

            if (!request.Completed.WaitOne(TimeSpan.FromSeconds(30)))
            {
                request.TimedOut = true;
                ResponseSerializer.WriteJson(context.Response, 500, BridgeResponse.Failure("internal_error", "bridge request timed out"));
                return;
            }

            ResponseSerializer.WriteJson(context.Response, request.StatusCode, request.Payload);
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
