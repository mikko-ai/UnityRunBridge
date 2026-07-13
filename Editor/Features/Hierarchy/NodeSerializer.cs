using System;
using System.Collections.Generic;
using Mk.UnityAgentBridge.Editor.Contracts;
using Mk.UnityAgentBridge.Editor.Json;
using UnityEngine;

namespace Mk.UnityAgentBridge.Editor.Hierarchy
{
    /// <summary>
    /// 节点序列化编排：Core 基础字段 + INodeEnricher 增强 + ITextControlAdapter 文本链。
    /// Phase 3 起不再直接引用 UGUI/TMP；正式实现位于 Adapter 程序集。
    /// </summary>
    internal static class NodeSerializer
    {
        public static JsonValue BuildSummary(Transform transform, IBridgeServiceResolver services = null)
        {
            services = BridgeServices.Current(services);
            GameObject go = transform.gameObject;
            JsonValue node = CoreNodeSerializer.BuildSummary(transform);

            ApplyEnrichersSummary(go, node, services);
            ApplyText(go, node, services);
            return node;
        }

        public static bool HasMissingScript(GameObject go)
        {
            return CoreNodeSerializer.HasMissingScript(go);
        }

        public static string TryGetText(GameObject go, IBridgeServiceResolver services = null)
        {
            services = BridgeServices.Current(services);
            if (services == null || go == null)
            {
                return null;
            }

            foreach (ITextControlAdapter adapter in services.GetAll<ITextControlAdapter>())
            {
                try
                {
                    if (adapter.TryGetText(go, out string text) && text != null)
                    {
                        return text;
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning(
                        $"Unity Agent Bridge: ITextControlAdapter {adapter.GetType().FullName} TryGetText 异常，已跳过：{ex.Message}");
                }
            }

            return null;
        }

        public static bool ComputeEffectiveInteractable(GameObject go, IBridgeServiceResolver services = null)
        {
            services = BridgeServices.Current(services);
            if (services != null && services.TryGet(out IInteractionBackend backend))
            {
                return backend.ComputeEffectiveInteractable(go);
            }

            // 无交互后端时视为可交互（非 UI 节点）。
            return true;
        }

        /// <summary>
        /// 保留旧测试/Pointer 兼容入口：优先走 UGUI enricher 写入的 screenRect 逻辑，
        /// 无服务时返回 false（不再内嵌 UGUI 实现）。
        /// </summary>
        public static bool TryComputeScreenRect(RectTransform rectTransform, out Rect rect)
        {
            rect = default;
            if (rectTransform == null)
            {
                return false;
            }

            IBridgeServiceResolver services = BridgeServices.Current();
            if (services == null)
            {
                return false;
            }

            JsonValue probe = JsonValue.NewObject();
            ApplyEnrichersSummary(rectTransform.gameObject, probe, services);
            if (!probe.TryGetObject("screenRect", out JsonValue rectJson))
            {
                return false;
            }

            rect = new Rect(
                (float)rectJson["x"].AsDouble,
                (float)rectJson["y"].AsDouble,
                (float)rectJson["w"].AsDouble,
                (float)rectJson["h"].AsDouble);
            return true;
        }

        public static bool TryGetInteractable(GameObject go, out bool interactable)
        {
            interactable = false;
            IBridgeServiceResolver services = BridgeServices.Current();
            if (services == null || go == null)
            {
                return false;
            }

            JsonValue probe = JsonValue.NewObject();
            ApplyEnrichersSummary(go, probe, services);
            if (!probe.TryGetBoolean("interactable", out interactable))
            {
                return false;
            }

            return true;
        }

        internal static void ApplyEnrichersSummary(GameObject go, JsonValue node, IBridgeServiceResolver services)
        {
            if (services == null || go == null || node == null)
            {
                return;
            }

            foreach (INodeEnricher enricher in services.GetAll<INodeEnricher>())
            {
                try
                {
                    enricher.EnrichSummary(go, node);
                }
                catch (Exception ex)
                {
                    Debug.LogWarning(
                        $"Unity Agent Bridge: INodeEnricher {enricher.GetType().FullName} EnrichSummary 异常，已跳过：{ex.Message}");
                }
            }
        }

        internal static void ApplyEnrichersInspection(GameObject go, JsonValue node, IBridgeServiceResolver services)
        {
            if (services == null || go == null || node == null)
            {
                return;
            }

            foreach (INodeEnricher enricher in services.GetAll<INodeEnricher>())
            {
                try
                {
                    enricher.EnrichInspection(go, node);
                }
                catch (Exception ex)
                {
                    Debug.LogWarning(
                        $"Unity Agent Bridge: INodeEnricher {enricher.GetType().FullName} EnrichInspection 异常，已跳过：{ex.Message}");
                }
            }
        }

        private static void ApplyText(GameObject go, JsonValue node, IBridgeServiceResolver services)
        {
            if (node.ContainsKey("text"))
            {
                return;
            }

            string text = TryGetText(go, services);
            if (text != null)
            {
                node["text"] = text;
            }
        }
    }
}
