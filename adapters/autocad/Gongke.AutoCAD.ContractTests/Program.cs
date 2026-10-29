using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using Gongke.AutoCAD;

int checks = 0;
void Check(bool condition, string name) { if (!condition) throw new Exception(name); checks++; }
void Rejected(Action action, string code)
{
    try { action(); throw new Exception($"Expected {code}"); }
    catch (BridgeException error) { Check(error.Code == code, $"Expected {code}, got {error.Code}"); }
}
var temporary = Path.Combine(Path.GetTempPath(), $"gongke-autocad-contract-{Guid.NewGuid():N}");
Directory.CreateDirectory(temporary);
try
{
    var request = Request.Parse("""{"id":"1","token":"secret","method":"host.describe","params":{}}""", "secret");
    Check(request.Method == "host.describe", "Parse method");
    Rejected(() => Request.Parse("""{"id":"1","token":"wrong","method":"host.describe"}""", "secret"), "unauthorized");
    Rejected(() => Request.Parse(new string(' ', 1_048_577), "secret"), "request_too_large");
    var target = Path.Combine(temporary, "copy.dwg");
    Check(FilePolicy.NewDwg(target) == target, "New DWG path");
    Rejected(() => FilePolicy.NewDwg("relative.dwg"), "invalid_path");
    var source = Path.Combine(temporary, "source.dxf");
    File.WriteAllText(source, "source sentinel");
    Check(FilePolicy.Existing(source, ".dxf") == source, "DXF source path");
    var staging = FilePolicy.Staging(target);
    File.WriteAllText(staging, "staged drawing");
    File.WriteAllText(target, "original sentinel");
    Rejected(() => FilePolicy.NewDwg(target), "destination_exists");
    try { FilePolicy.Publish(staging, target); throw new Exception("Overwrite was allowed"); }
    catch (IOException) { Check(File.ReadAllText(target) == "original sentinel", "Publish race preserves original"); }
    Check(File.ReadAllText(source) == "source sentinel", "Source unchanged");

    using var server = new BridgeServer(temporary);
    server.Start();
    using var descriptor = JsonDocument.Parse(File.ReadAllText(Path.Combine(temporary, $"autocad-{Environment.ProcessId}.json")));
    var pipeName = descriptor.RootElement.GetProperty("pipe_name").GetString()!;
    var token = descriptor.RootElement.GetProperty("token").GetString()!;
    Check(token.Length == 64, "Random connection token");
    async Task<JsonElement> Call(string id, string method, object parameters, string? suppliedToken = null)
    {
        await using var pipe = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
        await pipe.ConnectAsync(3000);
        using var reader = new StreamReader(pipe, Encoding.UTF8, false, 4096, true);
        await using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true) { AutoFlush = true };
        await writer.WriteLineAsync(JsonSerializer.Serialize(new { id, method, token = suppliedToken ?? token, @params = parameters }));
        var line = await reader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(5));
        using var json = JsonDocument.Parse(line!);
        return json.RootElement.Clone();
    }
    async Task WaitQueued()
    {
        var deadline = DateTime.UtcNow.AddSeconds(3);
        while (server.PendingCount == 0 && DateTime.UtcNow < deadline) await Task.Delay(10);
        Check(server.PendingCount > 0, "Host queue receives request");
    }
    var unauthorized = await Call("bad", "host.describe", new { }, "incorrect");
    Check(unauthorized.GetProperty("error").GetProperty("code").GetString() == "unauthorized", "Pipe token enforced");
    Check(server.PendingCount == 0, "Unauthorized request never reaches host");
    var args1 = new { operation_id = "edit-1", document_id = "doc", expected_revision = 4, handle = "A", text = "new note" };
    var editing = Call("edit", "drawing.edit_text", args1);
    await WaitQueued();
    Check(server.TryDequeue(out var pending) && pending is not null, "Queued work reaches host thread");
    var running = await Call("state", "operation.status", new { operation_id = "edit-1" });
    Check(running.GetProperty("result").GetProperty("status").GetString() == "running", "Status available while command executes");
    var cancelRunning = await Call("cancel-running", "operation.cancel", new { operation_id = "edit-1" });
    Check(!cancelRunning.GetProperty("result").GetProperty("cancelled").GetBoolean(), "Running native operation not interrupted");
    // Transport test completes a queue item without pretending to run Autodesk APIs.
    server.Complete(pending!, new { operation_id = "edit-1", outcome = "committed", transport_test_only = true });
    var completed = await editing;
    Check(completed.GetProperty("id").GetString() == "edit", "Original response ID");
    var duplicate = await Call("duplicate", "drawing.edit_text", args1);
    Check(duplicate.GetProperty("id").GetString() == "duplicate" && server.PendingCount == 0, "Duplicate receipt returns current request ID without reexecution");
    var conflict = await Call("conflict", "drawing.edit_text", new { operation_id = "edit-1", text = "different" });
    Check(conflict.GetProperty("error").GetProperty("code").GetString() == "operation_id_conflict", "Operation ID conflict rejected");
    var queued = Call("queued", "drawing.edit_text", new { operation_id = "edit-2" });
    await WaitQueued();
    var cancelled = await Call("cancel", "operation.cancel", new { operation_id = "edit-2" });
    Check(cancelled.GetProperty("result").GetProperty("cancelled").GetBoolean(), "Queued native operation can be cancelled");
    Check(!server.TryDequeue(out _), "Cancelled request never reaches host");
    Check((await queued).GetProperty("error").GetProperty("outcome").GetString() == "unchanged", "Cancelled command outcome unchanged");
    var unknown = await Call("unknown", "operation.status", new { operation_id = "other-session" });
    Check(unknown.GetProperty("result").GetProperty("outcome").GetString() == "unknown", "Missing receipt is not inferred unchanged");
    Check(Directory.GetFiles(temporary, "autocad-*.jsonl").Length == 1, "Operation journal persisted");
    Console.WriteLine($"PASS: {checks} protocol, transport, cancellation, receipt and no-overwrite checks. No AutoCAD host APIs executed.");
}
finally { Directory.Delete(temporary, true); }
