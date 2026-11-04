using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using Gongke.AutoCAD;

if (args.Length > 0 && args[0] == "--crash-child") { RecoveryChecks.Child(args[1], args[2]); return; }

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
    var unicode = new Request("fingerprint", "drawing.import_dxf", JsonSerializer.SerializeToElement(new {
        operation_id = "指纹-1", source_path = "C:\\课程\\😀\u0085\u2028\u2029\u001f.dxf", target_path = "C:\\副本.dwg" }));
    Check(OperationStore.Fingerprint(unicode) == "1759d0c6d11dbb879b8e78cd9509c73cecec422ac1979876257a5f9314e7d726",
        "Native fingerprint matches hosts.py including non-BMP and escaped characters");
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

    await RecoveryChecks.Run(temporary, Check);

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
    Check(Directory.GetFiles(Path.Combine(temporary, "autocad-operations"), "*.json").Length == 2, "Operation records persisted");
    var reordered = JsonSerializer.Deserialize<JsonElement>("""{"text":"new note","handle":"A","expected_revision":4,"document_id":"doc","operation_id":"edit-1"}""");
    var reorderedResult = await Call("reordered", "drawing.edit_text", reordered);
    Check(reorderedResult.GetProperty("result").GetProperty("status").GetString() == "completed", "Property order does not create a conflict");

    foreach (var phase in new[] { "queued", "running" })
    {
        var op = "io-failure-" + phase;
        var task = Call(op, "document.open", new { operation_id = op, path = "new.dwg" });
        await WaitQueued();
        BridgeServer.Pending? faultPending = null;
        if (phase == "running") Check(server.TryDequeue(out faultPending), "Start operation before completion failure");
        var path = server.Operations.RecordPath(op);
        File.Move(path, path + ".backup");
        Directory.CreateDirectory(path);
        if (phase == "queued") Check(!server.TryDequeue(out _), "Failed running barrier never reaches native API");
        else server.Complete(faultPending!, new { opened = true });
        var fault = await task;
        Check(fault.GetProperty("error").GetProperty("code").GetString() == "operation_store_unavailable", "Persistence failure visible to client");
        Check(fault.GetProperty("error").GetProperty("outcome").GetString() == (phase == "queued" ? "unchanged" : "unknown"), "Persistence failure outcome reflects execution phase");
        Directory.Delete(path);
        File.Move(path + ".backup", path);
        var recovered = await Call("recover", "operation.status", new { operation_id = op });
        Check(recovered.GetProperty("result").GetProperty("status").GetString() == (phase == "queued" ? "interrupted_before_start" : "interrupted"), "Last durable state governs recovery");
        var replay = await Call("retry", "document.open", new { operation_id = op, path = "new.dwg" });
        Check(server.PendingCount == 0 && replay.GetProperty("result").GetProperty("outcome").GetString() == (phase == "queued" ? "unchanged" : "unknown"), "Persistence failure never triggers replay");
    }
    var oldSession = server.Session;
    server.Dispose();
    using var restartedServer = new BridgeServer(temporary);
    restartedServer.Start();
    using var newDescriptor = JsonDocument.Parse(File.ReadAllText(Path.Combine(temporary, $"autocad-{Environment.ProcessId}.json")));
    token = newDescriptor.RootElement.GetProperty("token").GetString()!;
    var persisted = await Call("after-restart", "operation.status", new { operation_id = "edit-1" });
    Check(persisted.GetProperty("result").GetProperty("session_id").GetString() == oldSession && restartedServer.Session != oldSession,
        "New plugin session returns original receipt session");
    Check(persisted.GetProperty("result").GetProperty("response").GetProperty("id").GetString() == "edit", "Original response survives server restart");
    Console.WriteLine($"PASS: {checks} protocol, transport, cancellation, receipt and no-overwrite checks. No AutoCAD host APIs executed.");
}
finally { Directory.Delete(temporary, true); }
