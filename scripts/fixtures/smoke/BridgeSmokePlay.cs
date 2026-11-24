using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

public sealed class BridgeSmokePlay
{
    [UnityTest]
    public IEnumerator RunsInPlayMode()
    {
        yield return null;
        Assert.That(Application.isPlaying, Is.True);
    }
}
