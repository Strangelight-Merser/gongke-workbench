using System;
using System.Threading;
using System.Threading.Tasks;
using Gongke.SolidWorks;
using Newtonsoft.Json.Linq;

internal static class ReliabilityChecks
{
    public static int Run()
    {
        int count = 0;
        void Check(bool condition, string name) { if (!condition) throw new Exception(name); count++; }
        foreach (var method in new[] { "document.open", "document.activate", "selection.set", "parameter.change",
            "drawing.update", "document.save_copy", "document.save", "drawing.export" })
            Check(Protocol.Writes.Contains(method), method + " 必须记录操作回执");

        HostDispatcher nested = null;
        Task<JObject> second = null;
        int calls = 0;
        nested = new HostDispatcher(request => {
            calls++;
            if ((string)request["id"] == "first")
            {
                second = nested.Submit(new JObject { ["id"] = "second" });
                nested.OnIdle();
                Check(calls == 1 && !second.IsCompleted, "COM 消息泵重入不能执行第二个操作");
            }
            return new JObject { ["result"] = true };
        });
        using (nested)
        {
            var first = nested.Submit(new JObject { ["id"] = "first" });
            nested.OnIdle();
            Check(first.GetAwaiter().GetResult() != null && calls == 1, "外层操作完成");
            nested.OnIdle();
            Check(second.GetAwaiter().GetResult() != null && calls == 2, "下次 idle 才执行队列请求");
        }
        int failingCalls = 0;
        using (var dispatcher = new HostDispatcher(_ => {
            if (++failingCalls == 1) throw new Exception("COM fault");
            return new JObject { ["result"] = true };
        }))
        {
            var first = dispatcher.Submit(new JObject());
            dispatcher.OnIdle();
            Check((string)first.GetAwaiter().GetResult()["error"]["outcome"] == "unknown", "执行异常不能声称未改");
            var next = dispatcher.Submit(new JObject()); dispatcher.OnIdle();
            Check(next.GetAwaiter().GetResult() != null && failingCalls == 2, "异常后释放重入保护");
        }
        int timedCalls = 0;
        using (var dispatcher = new HostDispatcher(_ => { timedCalls++; return new JObject(); }, TimeSpan.FromMilliseconds(10)))
        {
            var timed = dispatcher.Submit(new JObject()).GetAwaiter().GetResult();
            dispatcher.OnIdle();
            Check((string)timed["error"]["outcome"] == "not_applied" && timedCalls == 0, "排队超时后绝不执行");
        }
        using (var dispatcher = new HostDispatcher(_ => {
            Thread.Sleep(100); return new JObject { ["result"] = true };
        }, TimeSpan.FromMilliseconds(10)))
        {
            var timed = dispatcher.Submit(new JObject()); dispatcher.OnIdle();
            Check((string)timed.GetAwaiter().GetResult()["error"]["outcome"] == "unknown", "执行中超时为未知，不能取消已发生的修改");
        }

        JObject Edit(string failure = "", bool finish = true, bool rebuild = true, bool change = true,
            int status = 0, double target = 2)
        {
            double value = 1;
            return ParameterEdit.Run(1, target, 0,
                () => { if (failure == "start") throw new Exception("start"); },
                () => { if (change) value = target; if (failure == "set") throw new Exception("set"); return status; },
                () => { if (failure == "rebuild") throw new Exception("rebuild"); return rebuild; },
                () => { if (failure == "finish") throw new Exception("finish"); return finish; },
                () => { if (failure == "read") throw new Exception("read"); return value; },
                () => { if (failure == "context") throw new Exception("context"); return new JObject { ["revision"] = 2 }; });
        }
        Check((string)Edit()["outcome"] == "applied", "成功写入、重建、Undo 和读回");
        foreach (var failure in new[] { "set", "rebuild", "finish", "context" })
        {
            var result = Edit(failure);
            Check((string)result["outcome"] == "needs_review" && (double)result["actual"] == 2,
                failure + " 异常后仍然读回已改尺寸");
            Check(((JArray)result["issues"]).Count == 1, failure + " 保留原故障");
        }
        Check((string)Edit("start")["outcome"] == "not_applied", "Undo 起始异常不调用 setter");
        Check((string)Edit("read")["outcome"] == "unknown", "读回失败不能宣称已验证");
        Check((string)Edit(finish: false)["outcome"] == "needs_review", "Undo 返回 false 必须告知用户");
        Check((string)Edit(rebuild: false)["outcome"] == "needs_review", "重建 false 仍可能已改");
        Check((string)Edit(status: 1)["outcome"] == "needs_review", "setter 失败码但尺寸已变");
        Check((string)Edit(change: false, status: 1)["outcome"] == "unknown", "原尺寸相同不证明文档整体没变");
        Check((string)Edit(target: 1)["outcome"] == "not_applied", "同值请求不修改");
        var doubleFailure = ParameterEdit.Run(1, 2, 0, () => { },
            () => throw new Exception("setter changed then failed"), () => true,
            () => throw new Exception("undo finish failed"), () => 2, () => new JObject());
        Check((string)doubleFailure["outcome"] == "needs_review" && ((JArray)doubleFailure["issues"]).Count == 2,
            "清理失败不覆盖 setter 故障或跳过读回");
        var invalidRead = ParameterEdit.Run(1, 2, 0, () => { }, () => 0, () => true,
            () => true, () => double.NaN, () => new JObject());
        Check((string)invalidRead["outcome"] == "unknown", "非有限读回不能当作成功或旧值");
        return count;
    }
}
