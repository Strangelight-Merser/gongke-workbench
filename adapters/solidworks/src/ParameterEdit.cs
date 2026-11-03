using System;
using Newtonsoft.Json.Linq;

namespace Gongke.SolidWorks
{
    // 把 COM 调用顺序与终态判定放在同一实现中；协议测试可注入各阶段的真实故障形态。
    internal static class ParameterEdit
    {
        public static JObject Run(double before, double target, int successStatus,
            Action startUndo, Func<int> set, Func<bool> rebuild, Func<bool> finishUndo,
            Func<double> readValue, Func<JObject> readDocument)
        {
            var issues = new JArray();
            var result = new JObject { ["before"] = before, ["requested"] = target,
                ["unit"] = "m", ["saved"] = false, ["rebuilt"] = false, ["undo_recorded"] = false };
            bool started = false, attempted = false;
            int? status = null;
            void Issue(string phase, Exception error) => issues.Add(new JObject {
                ["phase"] = phase, ["message"] = error.Message });
            var phase = "undo_start";
            try
            {
                // 无变化不制造一次重建或 Undo 记录。
                if (Math.Abs(before - target) > 1e-10)
                {
                    startUndo(); started = true;
                    phase = "set"; attempted = true; status = set();
                    phase = "rebuild"; result["rebuilt"] = rebuild();
                }
            }
            catch (Exception error) { Issue(phase, error); }
            finally
            {
                if (started)
                {
                    try { result["undo_recorded"] = finishUndo(); }
                    catch (Exception error) { Issue("undo_finish", error); }
                }
            }
            // FinishRecordingUndoObject2 不是回滚；即使 set/rebuild/finish 抛错也必须读回。
            double? actual = null;
            try
            {
                var value = readValue();
                if (double.IsNaN(value) || double.IsInfinity(value)) throw new InvalidOperationException("尺寸读回不是有限数值。");
                actual = value;
            }
            catch (Exception error) { Issue("readback", error); }
            try { result["document"] = readDocument(); }
            catch (Exception error) { Issue("document_readback", error); }
            var matches = actual.HasValue && Math.Abs(actual.Value - target) <= 1e-10;
            var changed = actual.HasValue && Math.Abs(actual.Value - before) > 1e-10;
            // 写入尝试后只读到旧尺寸不能证明整个文档未变；保留 unknown，禁止自动重试。
            var outcome = !attempted ? "not_applied" : !actual.HasValue ? "unknown"
                : changed ? (matches && status == successStatus && (bool)result["rebuilt"]
                    && (bool)result["undo_recorded"] && issues.Count == 0 ? "applied" : "needs_review") : "unknown";
            result["set_status"] = status;
            result["actual"] = actual;
            result["readback_matches"] = matches;
            result["outcome"] = outcome;
            result["status"] = outcome;
            result["issues"] = issues;
            return result;
        }
    }
}
