using System;

namespace Mk.UnityAgentBridge.Editor.Tests.Gameplay
{
    /// <summary>
    /// 测试专用 duck-typed attribute：与游戏侧自定义 attribute 的用法完全一致——
    /// 只要类型短名是 "AgentCommandAttribute" 即被 GameplayCommandRegistry 识别，
    /// 不依赖 Mk.UnityAgentBridge 包本身，验证「零侵入」约定。
    /// </summary>
    [AttributeUsage(AttributeTargets.Method)]
    public sealed class AgentCommandAttribute : Attribute
    {
        public string Name { get; set; }
    }

    /// <summary>白名单直调测试用：方法名重载，验证 AmbiguousMatchException 分支。</summary>
    internal static class OverloadedGameplayCommands
    {
        public static void Foo(int a)
        {
        }

        public static void Foo(string a)
        {
        }
    }

    internal static class SampleGameplayCommands
    {
        public enum SampleEnum
        {
            A,
            B,
            C
        }

        [AgentCommand]
        public static int AddGold(int amount)
        {
            return amount + 1;
        }

        [AgentCommand(Name = "custom.name")]
        public static void DoSomething()
        {
        }

        [AgentCommand]
        public static void UnsupportedParam(UnityEngine.Vector3 position)
        {
        }

        [AgentCommand]
        public static SampleEnum EchoEnum(SampleEnum value)
        {
            return value;
        }

        [AgentCommand]
        public static object UnsupportedReturnType()
        {
            return null;
        }
    }
}
