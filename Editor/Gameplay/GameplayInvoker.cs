using System;
using System.Diagnostics;
using System.Reflection;
using Mk.UnityAgentBridge.Editor.Json;

namespace Mk.UnityAgentBridge.Editor.Gameplay
{
    /// <summary>
    /// 参数类型转换 + 方法调用的纯逻辑，不依赖 Play Mode 或 HTTP 上下文，便于 EditMode 测试
    /// 直接覆盖（GameplayController 只负责门禁与 JSON 编解码，实际调用委派到这里）。
    /// </summary>
    internal static class GameplayInvoker
    {
        public sealed class InvokeResult
        {
            public bool Ok;
            public JsonValue ResultJson;
            public string ErrorCode;
            public string ErrorMessage;
            public long DurationMs;

            public static InvokeResult Success(JsonValue resultJson, long durationMs)
            {
                return new InvokeResult { Ok = true, ResultJson = resultJson, DurationMs = durationMs };
            }

            public static InvokeResult Fail(string code, string message, long durationMs)
            {
                return new InvokeResult { Ok = false, ErrorCode = code, ErrorMessage = message, DurationMs = durationMs };
            }
        }

        public static bool TryBuildArguments(
            GameplayCommandRegistry.CommandInfo command, JsonValue args, out object[] callArgs, out string errorCode, out string errorMessage)
        {
            ParameterInfo[] parameters = command.Method.GetParameters();
            callArgs = new object[parameters.Length];
            errorCode = null;
            errorMessage = null;

            for (int i = 0; i < parameters.Length; i++)
            {
                ParameterInfo parameter = parameters[i];
                if (args == null || !args.IsObject || !args.TryGet(parameter.Name, out JsonValue rawValue))
                {
                    errorCode = "invalid_argument";
                    errorMessage = $"缺少参数：{parameter.Name}";
                    return false;
                }

                if (!TryConvertArgument(rawValue, parameter.ParameterType, out object converted, out string conversionError))
                {
                    errorCode = "invalid_argument";
                    errorMessage = $"参数 {parameter.Name} 类型错误：{conversionError}";
                    return false;
                }

                callArgs[i] = converted;
            }

            return true;
        }

        public static InvokeResult Invoke(GameplayCommandRegistry.CommandInfo command, object[] callArgs)
        {
            Stopwatch stopwatch = Stopwatch.StartNew();
            object rawResult;
            try
            {
                rawResult = command.Method.Invoke(null, callArgs);
            }
            catch (TargetInvocationException ex)
            {
                stopwatch.Stop();
                Exception inner = ex.InnerException ?? ex;
                return InvokeResult.Fail(
                    "invoke_failed",
                    $"命令执行抛出异常：{inner.GetType().Name}: {inner.Message}",
                    stopwatch.ElapsedMilliseconds);
            }

            stopwatch.Stop();
            JsonValue resultJson = ConvertResultToJson(rawResult, command.ReturnType);
            return InvokeResult.Success(resultJson, stopwatch.ElapsedMilliseconds);
        }

        internal static bool TryConvertArgument(JsonValue value, Type targetType, out object converted, out string error)
        {
            converted = null;
            error = null;

            if (targetType == typeof(bool))
            {
                if (!value.IsBoolean)
                {
                    error = "期望 bool";
                    return false;
                }

                converted = value.AsBoolean;
                return true;
            }

            if (targetType == typeof(int))
            {
                if (!value.IsNumber)
                {
                    error = "期望数字";
                    return false;
                }

                converted = value.AsInt;
                return true;
            }

            if (targetType == typeof(long))
            {
                if (!value.IsNumber)
                {
                    error = "期望数字";
                    return false;
                }

                converted = value.AsLong;
                return true;
            }

            if (targetType == typeof(float))
            {
                if (!value.IsNumber)
                {
                    error = "期望数字";
                    return false;
                }

                converted = value.AsFloat;
                return true;
            }

            if (targetType == typeof(double))
            {
                if (!value.IsNumber)
                {
                    error = "期望数字";
                    return false;
                }

                converted = value.AsDouble;
                return true;
            }

            if (targetType == typeof(string))
            {
                if (!value.IsString)
                {
                    error = "期望字符串";
                    return false;
                }

                converted = value.AsString;
                return true;
            }

            if (targetType.IsEnum)
            {
                if (value.IsString)
                {
                    try
                    {
                        converted = Enum.Parse(targetType, value.AsString, ignoreCase: true);
                        return true;
                    }
                    catch (Exception)
                    {
                        error = $"不是合法的枚举值：{value.AsString}";
                        return false;
                    }
                }

                if (value.IsNumber)
                {
                    converted = Enum.ToObject(targetType, value.AsLong);
                    return true;
                }

                error = "期望枚举名（字符串）或整数";
                return false;
            }

            error = $"不支持的目标类型：{targetType.FullName}";
            return false;
        }

        internal static JsonValue ConvertResultToJson(object result, string returnType)
        {
            if (returnType == "void" || result == null)
            {
                return JsonValue.Null;
            }

            switch (result)
            {
                case bool boolValue:
                    return JsonValue.FromBoolean(boolValue);
                case int intValue:
                    return JsonValue.FromInteger(intValue);
                case long longValue:
                    return JsonValue.FromInteger(longValue);
                case float floatValue:
                    return JsonValue.FromDouble(floatValue);
                case double doubleValue:
                    return JsonValue.FromDouble(doubleValue);
                case string stringValue:
                    return JsonValue.FromString(stringValue);
                case Enum enumValue:
                    return JsonValue.FromString(enumValue.ToString());
                default:
                    return JsonValue.FromString(result.ToString());
            }
        }
    }
}
