using System;
using System.Reflection;
using UnityEngine;
using UnityRunBridge.Examples;

// Benchmark-only reset. Not distributed with the Bridge or run in a game project.
public static class UiLocateBaselineReset
{
    public static string Reset()
    {
        var demo = UnityEngine.Object.FindObjectOfType<UiReviewDemo>();
        if (demo == null)
            throw new InvalidOperationException("UI benchmark demo is missing.");
        var close = typeof(UiReviewDemo).GetMethod("Close", BindingFlags.Instance | BindingFlags.NonPublic);
        if (close == null)
            throw new InvalidOperationException("UI benchmark reset is missing.");
        close.Invoke(demo, null);
        return UiReviewDemo.FocusedControl();
    }
}
