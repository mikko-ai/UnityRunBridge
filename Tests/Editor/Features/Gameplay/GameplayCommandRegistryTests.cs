using System;
using System.Linq;
using Mk.UnityAgentBridge.Editor.Gameplay;
using NUnit.Framework;

namespace Mk.UnityAgentBridge.Editor.Tests.Gameplay
{
    public sealed class GameplayCommandRegistryTests
    {
        [SetUp]
        public void ResetCache()
        {
            GameplayCommandRegistry.ResetCacheForTests();
        }

        [Test]
        public void DiscoverAttributeCommands_FindsMethodWithDefaultName()
        {
            var command = GameplayCommandRegistry.DiscoverAttributeCommands()
                .FirstOrDefault(c => c.Name == "SampleGameplayCommands.AddGold");

            Assert.IsNotNull(command);
            Assert.IsTrue(command.Invocable);
            Assert.AreEqual("attribute", command.Source);
            Assert.AreEqual(1, command.Parameters.Count);
            Assert.AreEqual("amount", command.Parameters[0].Name);
            Assert.AreEqual("int", command.Parameters[0].Type);
            Assert.AreEqual("int", command.ReturnType);
        }

        [Test]
        public void DiscoverAttributeCommands_UsesCustomNameFromAttribute()
        {
            var commands = GameplayCommandRegistry.DiscoverAttributeCommands();

            Assert.IsTrue(commands.Any(c => c.Name == "custom.name"));
            Assert.IsFalse(commands.Any(c => c.Name == "SampleGameplayCommands.DoSomething"));
        }

        [Test]
        public void DiscoverAttributeCommands_UnsupportedParameterType_MarksNotInvocable()
        {
            var command = GameplayCommandRegistry.DiscoverAttributeCommands()
                .FirstOrDefault(c => c.Name == "SampleGameplayCommands.UnsupportedParam");

            Assert.IsNotNull(command);
            Assert.IsFalse(command.Invocable);
            Assert.IsNotNull(command.InvocableReason);
        }

        [Test]
        public void DiscoverAttributeCommands_UnsupportedReturnType_MarksNotInvocable()
        {
            var command = GameplayCommandRegistry.DiscoverAttributeCommands()
                .FirstOrDefault(c => c.Name == "SampleGameplayCommands.UnsupportedReturnType");

            Assert.IsNotNull(command);
            Assert.IsFalse(command.Invocable);
            StringAssert.Contains("返回值", command.InvocableReason);
        }

        [Test]
        public void DiscoverAttributeCommands_EnumParameterAndReturnType_AreSupported()
        {
            var command = GameplayCommandRegistry.DiscoverAttributeCommands()
                .FirstOrDefault(c => c.Name == "SampleGameplayCommands.EchoEnum");

            Assert.IsNotNull(command);
            Assert.IsTrue(command.Invocable);
            StringAssert.StartsWith("enum:", command.Parameters[0].Type);
            StringAssert.StartsWith("enum:", command.ReturnType);
        }

        [Test]
        public void Resolve_MatchesAttributeCommandFirst()
        {
            bool ok = GameplayCommandRegistry.Resolve(
                "SampleGameplayCommands.AddGold", Array.Empty<string>(),
                out GameplayCommandRegistry.CommandInfo command, out string _, out string _);

            Assert.IsTrue(ok);
            Assert.AreEqual("attribute", command.Source);
        }

        [Test]
        public void Resolve_FallsBackToWhitelistWhenNoAttributeMatch()
        {
            string fqn = typeof(SampleGameplayCommands).FullName + ".AddGold";

            bool ok = GameplayCommandRegistry.Resolve(
                fqn, new[] { fqn }, out GameplayCommandRegistry.CommandInfo command, out string _, out string _);

            Assert.IsTrue(ok);
            Assert.AreEqual("whitelist", command.Source);
        }

        [Test]
        public void TryResolveWhitelistCommand_NotInWhitelist_ReturnsCommandNotFound()
        {
            bool ok = GameplayCommandRegistry.TryResolveWhitelistCommand(
                "Foo.Bar.Baz", new[] { "Other.Thing.Method" },
                out GameplayCommandRegistry.CommandInfo _, out string code, out string message);

            Assert.IsFalse(ok);
            Assert.AreEqual("command_not_found", code);
            Assert.IsNotNull(message);
        }

        [Test]
        public void TryResolveWhitelistCommand_ResolvesTypeAndMethod()
        {
            string fqn = typeof(SampleGameplayCommands).FullName + ".AddGold";

            bool ok = GameplayCommandRegistry.TryResolveWhitelistCommand(
                fqn, new[] { fqn }, out GameplayCommandRegistry.CommandInfo command, out string _, out string _);

            Assert.IsTrue(ok);
            Assert.AreEqual("whitelist", command.Source);
            Assert.AreEqual("AddGold", command.Method.Name);
        }

        [Test]
        public void TryResolveWhitelistCommand_TypeNotFound_ReturnsCommandNotFound()
        {
            const string fqn = "No.Such.Namespace.NoSuchType.Method";

            bool ok = GameplayCommandRegistry.TryResolveWhitelistCommand(
                fqn, new[] { fqn }, out GameplayCommandRegistry.CommandInfo _, out string code, out string _);

            Assert.IsFalse(ok);
            Assert.AreEqual("command_not_found", code);
        }

        [Test]
        public void TryResolveWhitelistCommand_MethodNotFound_ReturnsCommandNotFound()
        {
            string fqn = typeof(SampleGameplayCommands).FullName + ".NoSuchMethod";

            bool ok = GameplayCommandRegistry.TryResolveWhitelistCommand(
                fqn, new[] { fqn }, out GameplayCommandRegistry.CommandInfo _, out string code, out string _);

            Assert.IsFalse(ok);
            Assert.AreEqual("command_not_found", code);
        }

        [Test]
        public void TryResolveWhitelistCommand_OverloadedMethod_ReturnsUnsupportedSignature()
        {
            string fqn = typeof(OverloadedGameplayCommands).FullName + ".Foo";

            bool ok = GameplayCommandRegistry.TryResolveWhitelistCommand(
                fqn, new[] { fqn }, out GameplayCommandRegistry.CommandInfo _, out string code, out string _);

            Assert.IsFalse(ok);
            Assert.AreEqual("unsupported_signature", code);
        }

        [Test]
        public void TryResolveWhitelistCommand_MalformedFullyQualifiedName_ReturnsCommandNotFound()
        {
            bool ok = GameplayCommandRegistry.TryResolveWhitelistCommand(
                "NoDotsHere", new[] { "NoDotsHere" }, out GameplayCommandRegistry.CommandInfo _, out string code, out string _);

            Assert.IsFalse(ok);
            Assert.AreEqual("command_not_found", code);
        }
    }
}
