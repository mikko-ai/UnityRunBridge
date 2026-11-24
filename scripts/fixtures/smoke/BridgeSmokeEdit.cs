using NUnit.Framework;

public sealed class BridgeSmokeEdit
{
    [Test] public void Passes() => Assert.AreEqual(2, 1 + 1);
    [Test] public void Fails() => Assert.Fail("Intentional UTF smoke failure");
}
