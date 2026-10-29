using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Gongke.SolidWorks;
using Newtonsoft.Json.Linq;

var count = 0;
void Check(bool result, string name) { if (!result) throw new Exception(name); count++; }
void Reject(Action action, string name) { try { action(); } catch (CommandError) { count++; return; } throw new Exception(name); }
Reject(() => Protocol.Required(new JObject(), "x"), "missing required field");
Reject(() => Protocol.Number(new JObject { ["v"] = "4" }, "v"), "string is not a number");
Reject(() => Protocol.Number(new JObject { ["v"] = double.NaN }, "v"), "NaN rejected");
Reject(() => Protocol.OperationId(new JObject { ["operation_id"] = "../escape" }), "receipt path cannot escape");
var id = Guid.NewGuid().ToString("D");
Check(Protocol.OperationId(new JObject { ["operation_id"] = id.ToUpperInvariant() }) == id, "canonical UUID");
var left = JObject.Parse("{\"b\":1,\"a\":{\"y\":2,\"x\":3}}");
var right = JObject.Parse("{\"a\":{\"x\":3,\"y\":2},\"b\":1}");
Check(Protocol.Fingerprint("change", left) == Protocol.Fingerprint("change", right), "key order independent fingerprint");
Check(Protocol.Fingerprint("save", left) != Protocol.Fingerprint("change", left), "method binds fingerprint");
right["b"] = 2;
Check(Protocol.Fingerprint("change", left) != Protocol.Fingerprint("change", right), "value binds fingerprint");
var root = Path.Combine(Path.GetTempPath(), "gongke-sw-test-" + id);
Directory.CreateDirectory(root);
try
{
    var journal = new OperationJournal(root);
    Check(journal.Get(id) == null, "missing receipt");
    journal.Put(id, new JObject { ["state"] = "started" });
    Check((string)new OperationJournal(root).Get(id)["state"] == "started", "started receipt survives recreation");
    journal.Put(id, new JObject { ["state"] = "finished", ["response"] = new JObject { ["ok"] = true } });
    Check((bool)journal.Get(id)["response"]["ok"], "final receipt atomically replaces started receipt");
    var output = Path.Combine(root, "part.sldprt");
    var parameters = new JObject { ["output_path"] = output };
    Check(Protocol.NewOutputPath(parameters, ".sldprt") == output, "new output accepted");
    File.WriteAllText(output, "original");
    Reject(() => Protocol.NewOutputPath(parameters, ".sldprt"), "existing output rejected");
    Check(File.ReadAllText(output) == "original", "existing output preserved");
    var executedOn = -1;
    var hostThread = Thread.CurrentThread.ManagedThreadId;
    using (var dispatcher = new HostDispatcher(request => { executedOn = Thread.CurrentThread.ManagedThreadId; return new JObject { ["id"] = request["id"], ["result"] = true }; }))
    {
        var task = dispatcher.Submit(new JObject { ["id"] = "test" });
        Check(executedOn == -1, "network enqueue does not execute host work");
        Task.Run(() => dispatcher.OnIdle()).GetAwaiter().GetResult();
        Check(executedOn == -1, "wrong thread cannot drain host queue");
        dispatcher.OnIdle();
        Check(task.GetAwaiter().GetResult()["result"].Value<bool>() && executedOn == hostThread, "host idle drains on owning thread");
        var queued = dispatcher.Submit(new JObject { ["id"] = "cancel" });
        dispatcher.Dispose();
        Check((string)queued.GetAwaiter().GetResult()["error"]["outcome"] == "not_applied", "unload cancels queued requests");
    }
}
finally { Directory.Delete(root, true); }
Console.WriteLine($"{count} protocol, receipt, and dispatch checks passed. No SOLIDWORKS host behavior was exercised.");
