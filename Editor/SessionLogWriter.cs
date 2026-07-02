using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor
{
    internal sealed class SessionLogWriter : IDisposable
    {
        private readonly StreamWriter writer;

        public string LogPath { get; }

        public SessionLogWriter(string logPath)
        {
            LogPath = logPath;
            Directory.CreateDirectory(Path.GetDirectoryName(logPath));
            writer = new StreamWriter(new FileStream(logPath, FileMode.Append, FileAccess.Write, FileShare.ReadWrite));
            writer.AutoFlush = true;
        }

        /// <summary>
        /// sequence 由调用方（SessionController）传入并负责持久化，
        /// 这样 domain reload 后可以从上次的值继续，保证单个 session 内单调递增。
        /// </summary>
        public void Write(string condition, string stackTrace, LogType type, int sequence)
        {
            SessionLogEntry entry = new SessionLogEntry
            {
                time = DateTime.UtcNow.ToString("o"),
                sequence = sequence,
                type = type.ToString(),
                message = condition ?? string.Empty,
                stackTrace = stackTrace ?? string.Empty,
                isPlayMode = EditorApplication.isPlaying,
                playModeFrame = EditorApplication.isPlaying ? Time.frameCount : -1,
                scenePath = EditorSceneManager.GetActiveScene().path ?? string.Empty
            };
            writer.WriteLine(JsonUtility.ToJson(entry));
        }

        public void Dispose()
        {
            writer.Flush();
            writer.Dispose();
        }

        [Serializable]
        private sealed class SessionLogEntry
        {
            public string time;
            public int sequence;
            public string type;
            public string message;
            public string stackTrace;
            public bool isPlayMode;
            public int playModeFrame;
            public string scenePath;
        }
    }
}
