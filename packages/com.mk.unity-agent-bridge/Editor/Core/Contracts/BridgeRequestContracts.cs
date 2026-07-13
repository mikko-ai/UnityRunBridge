using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Json;

namespace Mk.UnityAgentBridge.Editor.Contracts
{
    /// <summary>路由处理委托：接收 Core 抽象的请求上下文，返回响应载荷。</summary>
    public delegate object BridgeRouteHandler(IBridgeRequestContext context);

    /// <summary>路由登记契约：Module 在 RegisterRoutes 阶段通过它把 handler 映射到 method+path。</summary>
    public interface IRouteRegistrar
    {
        void Map(string method, string pathPattern, BridgeRouteHandler handler);
    }

    /// <summary>
    /// 请求上下文契约：不暴露 HttpListenerRequest，Host 负责把网络请求转换为该抽象，
    /// Feature handler 不泄漏 Host 类型。
    /// </summary>
    public interface IBridgeRequestContext
    {
        string PathParam { get; }
        string RawBody { get; }
        JsonValue Body { get; }
        IReadOnlyDictionary<string, string> QueryParams { get; }
        bool HasQuery(string key);
        string GetQuery(string key, string defaultValue = null);
        int GetQueryInt(string key, int defaultValue);
        bool GetQueryBool(string key, bool defaultValue);
    }
}
