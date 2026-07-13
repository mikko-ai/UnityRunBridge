using System;
using System.Collections.Generic;
using System.Reflection;
using Mk.UnityAgentBridge.Editor.Gameplay;
using Mk.UnityAgentBridge.Editor.Json;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Gameplay
{
    public sealed class GameplayInvokerTests
    {
        private enum SampleEnum
        {
            A,
            B,
            C
        }

        private static int AddInts(int a, int b) => a + b;
        private static bool NegateBool(bool value) => !value;
        private static SampleEnum EchoEnum(SampleEnum value) => value;
        private static void ThrowsException() => throw new InvalidOperationException("boom");
        private static void NoOp()
        {
        }

        private static GameplayCommandRegistry.CommandInfo MakeCommand(string methodName, string returnType)
        {
            MethodInfo method = typeof(GameplayInvokerTests).GetMethod(
                methodName, BindingFlags.NonPublic | BindingFlags.Static);

            List<GameplayCommandRegistry.ParamInfo> parameters = new List<GameplayCommandRegistry.ParamInfo>();
            foreach (ParameterInfo parameter in method.GetParameters())
            {
                parameters.Add(new GameplayCommandRegistry.ParamInfo { Name = parameter.Name, Type = parameter.ParameterType.Name });
            }

            return new GameplayCommandRegistry.CommandInfo
            {
                Name = methodName,
                AssemblyName = "Test",
                Method = method,
                Parameters = parameters,
                ReturnType = returnType,
                Source = "attribute",
                Invocable = true
            };
        }

        [Test]
        public void TryBuildArguments_ConvertsJsonNumberToInt()
        {
            GameplayCommandRegistry.CommandInfo command = MakeCommand(nameof(AddInts), "int");
            JsonValue args = JsonParser.Parse(@"{""a"": 2, ""b"": 3}");

            bool ok = GameplayInvoker.TryBuildArguments(command, args, out object[] callArgs, out string _, out string _);

            Assert.IsTrue(ok);
            Assert.AreEqual(2, callArgs[0]);
            Assert.AreEqual(3, callArgs[1]);
        }

        [Test]
        public void TryBuildArguments_MissingParameter_ReturnsInvalidArgument()
        {
            GameplayCommandRegistry.CommandInfo command = MakeCommand(nameof(AddInts), "int");
            JsonValue args = JsonParser.Parse(@"{""a"": 2}");

            bool ok = GameplayInvoker.TryBuildArguments(command, args, out object[] _, out string code, out string message);

            Assert.IsFalse(ok);
            Assert.AreEqual("invalid_argument", code);
            StringAssert.Contains("b", message);
        }

        [Test]
        public void TryBuildArguments_WrongJsonType_ReturnsInvalidArgument()
        {
            GameplayCommandRegistry.CommandInfo command = MakeCommand(nameof(NegateBool), "bool");
            JsonValue args = JsonParser.Parse(@"{""value"": ""not-a-bool""}");

            bool ok = GameplayInvoker.TryBuildArguments(command, args, out object[] _, out string code, out string _);

            Assert.IsFalse(ok);
            Assert.AreEqual("invalid_argument", code);
        }

        [Test]
        public void TryBuildArguments_EnumFromString_ParsesByName()
        {
            GameplayCommandRegistry.CommandInfo command = MakeCommand(nameof(EchoEnum), "enum:SampleEnum");
            JsonValue args = JsonParser.Parse(@"{""value"": ""B""}");

            bool ok = GameplayInvoker.TryBuildArguments(command, args, out object[] callArgs, out string _, out string _);

            Assert.IsTrue(ok);
            Assert.AreEqual(SampleEnum.B, callArgs[0]);
        }

        [Test]
        public void TryBuildArguments_EnumFromNumber_ParsesByOrdinal()
        {
            GameplayCommandRegistry.CommandInfo command = MakeCommand(nameof(EchoEnum), "enum:SampleEnum");
            JsonValue args = JsonParser.Parse(@"{""value"": 2}");

            bool ok = GameplayInvoker.TryBuildArguments(command, args, out object[] callArgs, out string _, out string _);

            Assert.IsTrue(ok);
            Assert.AreEqual(SampleEnum.C, callArgs[0]);
        }

        [Test]
        public void TryBuildArguments_InvalidEnumName_ReturnsInvalidArgument()
        {
            GameplayCommandRegistry.CommandInfo command = MakeCommand(nameof(EchoEnum), "enum:SampleEnum");
            JsonValue args = JsonParser.Parse(@"{""value"": ""NotAMember""}");

            bool ok = GameplayInvoker.TryBuildArguments(command, args, out object[] _, out string code, out string _);

            Assert.IsFalse(ok);
            Assert.AreEqual("invalid_argument", code);
        }

        [Test]
        public void Invoke_ReturnsResultJsonAndDuration()
        {
            GameplayCommandRegistry.CommandInfo command = MakeCommand(nameof(AddInts), "int");

            GameplayInvoker.InvokeResult result = GameplayInvoker.Invoke(command, new object[] { 2, 3 });

            Assert.IsTrue(result.Ok);
            Assert.AreEqual(5, result.ResultJson.AsInt);
            Assert.GreaterOrEqual(result.DurationMs, 0);
        }

        [Test]
        public void Invoke_MethodThrows_ReturnsInvokeFailed()
        {
            GameplayCommandRegistry.CommandInfo command = MakeCommand(nameof(ThrowsException), "void");

            GameplayInvoker.InvokeResult result = GameplayInvoker.Invoke(command, Array.Empty<object>());

            Assert.IsFalse(result.Ok);
            Assert.AreEqual("invoke_failed", result.ErrorCode);
            StringAssert.Contains("boom", result.ErrorMessage);
        }

        [Test]
        public void Invoke_VoidMethod_ReturnsNullResult()
        {
            GameplayCommandRegistry.CommandInfo command = MakeCommand(nameof(NoOp), "void");

            GameplayInvoker.InvokeResult result = GameplayInvoker.Invoke(command, Array.Empty<object>());

            Assert.IsTrue(result.Ok);
            Assert.IsTrue(result.ResultJson.IsNull);
        }
    }
}
