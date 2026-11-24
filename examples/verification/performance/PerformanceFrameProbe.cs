using UnityEngine;

namespace UnityRunBridge.Examples
{
    // Copy to the development project only. Expose just these two methods through the whitelist.
    public static class PerformanceFrameProbe
    {
        private static int markedFrame = -1;

        public static int Mark()
        {
            markedFrame = Time.frameCount;
            return markedFrame;
        }

        public static int FramesSinceMark()
        {
            return markedFrame < 0 ? -1 : Time.frameCount - markedFrame;
        }
    }
}
