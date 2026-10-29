using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO.Pipes;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Gongke.AutoCAD;

internal sealed class BridgeServer : IDisposable
{
    private readonly CancellationTokenSource stop = new();
    private readonly ConcurrentQueue<Pending> queue = new();
    private readonly ConcurrentDictionary<string, Receipt> receipts = new();
    private readonly string token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
    private readonly string pipeName = $"gongke-autocad-{Environment.ProcessId}";
    private readonly string session = Guid.NewGuid().ToString("N");
    private readonly string folder;
    private readonly string descriptor;
    private readonly string journal;
    private readonly object journalLock = new();
    internal static readonly HashSet<string> Mutations = ["drawing.edit_text", "drawing.move_dimension_text", "drawing.import_dxf", "document.save_copy"];
    internal string Session => session;
    internal int PendingCount => queue.Count;

    internal BridgeServer(string? discoveryFolder = null)
    {
        folder = discoveryFolder ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Gongke", "hosts");
        Directory.CreateDirectory(folder);
        descriptor = Path.Combine(folder, $"autocad-{Environment.ProcessId}.json");
        journal = Path.Combine(folder, $"autocad-{session}.jsonl");
    }

    internal void Start()
    {
        File.WriteAllText(descriptor, JsonSerializer.Serialize(new {
            host_id = $"autocad-{session}", host = "autocad", instance_id = session, pid = Environment.ProcessId,
            transport = "named_pipe", pipe_name = pipeName, token, protocol_version = 1,
            started_at = DateTimeOffset.UtcNow, validation_level = "sdk_compiled_host_unverified"
        }));
        _ = Task.Run(Listen);
    }

    private async Task Listen()
    {
        while (!stop.IsCancellationRequested)
        {
            try
            {
                var pipe = new NamedPipeServerStream(pipeName, PipeDirection.InOut, 8,
                    PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                try { await pipe.WaitForConnectionAsync(stop.Token); }
                catch { pipe.Dispose(); throw; }
                _ = HandleClient(pipe);
            }
            catch (OperationCanceledException) when (stop.IsCancellationRequested) { break; }
            catch (Exception e)
            {
                Log(new { event_name = "transport_error", message = e.Message, at = DateTimeOffset.UtcNow });
                await Task.Delay(1000, stop.Token).ConfigureAwait(false);
            }
        }
    }

    private async Task HandleClient(NamedPipeServerStream pipe)
    {
        await using (pipe)
        {
            try
            {
                using var reader = new StreamReader(pipe, new UTF8Encoding(false), false, 4096, true);
                await using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true) { AutoFlush = true };
                while (pipe.IsConnected && !stop.IsCancellationRequested)
                {
                    var line = await reader.ReadLineAsync(stop.Token);
                    if (line is null) break;
                    object response;
                    string? id = null;
                    try
                    {
                        var request = Request.Parse(line, token);
                        id = request.Id;
                        response = await Submit(request);
                    }
                    catch (BridgeException e) { response = Error(id, e.Code, e.Message, e.Outcome); }
                    catch (Exception e) when (e is JsonException or InvalidOperationException or KeyNotFoundException or FormatException)
                    { response = Error(id, "invalid_request", e.Message, "unchanged"); }
                    await writer.WriteLineAsync(JsonSerializer.Serialize(response));
                }
            }
            catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
            catch (IOException) { /* Client disconnect does not cancel or replay a host operation. */ }
            catch (Exception e)
            {
                Log(new { event_name = "transport_error", message = e.Message, at = DateTimeOffset.UtcNow });
            }
        }
    }

    private Task<object> Submit(Request request)
    {
        if (request.Method == "operation.status")
        {
            var operationId = request.Params.NonEmpty("operation_id");
            return Task.FromResult<object>(new { id = request.Id, result = receipts.TryGetValue(operationId, out var found)
                ? (object)new { operation_id = operationId, status = found.Status, outcome = found.Outcome, response = found.Response }
                : new { operation_id = operationId, status = "unknown", outcome = "unknown", response = (object?)null } });
        }
        if (request.Method == "operation.cancel")
        {
            var operationId = request.Params.NonEmpty("operation_id");
            var cancelled = receipts.TryGetValue(operationId, out var receipt) && receipt.Pending?.TryCancel() == true;
            return Task.FromResult<object>(new { id = request.Id, result = new { operation_id = operationId, cancelled,
                outcome = cancelled ? "unchanged" : "unknown", status = cancelled ? "cancelled_before_start" : "not_cancelled" } });
        }
        string? op = null;
        if (Mutations.Contains(request.Method))
        {
            op = request.Params.NonEmpty("operation_id");
            var key = request.Method + "\n" + request.Params.GetRawText();
            var receipt = new Receipt(key);
            if (!receipts.TryAdd(op, receipt))
            {
                var existing = receipts[op];
                if (existing.RequestKey != key) throw new BridgeException("operation_id_conflict", "Operation ID was already used for a different request.");
                return Task.FromResult<object>(new { id = request.Id, result = new { operation_id = op,
                    status = existing.Status, outcome = existing.Outcome, response = existing.Response, replayed = false } });
            }
            Log(new { operation_id = op, method = request.Method, status = "queued", outcome = "unknown", at = DateTimeOffset.UtcNow });
        }
        var pending = new Pending(request, op);
        if (op is not null) receipts[op].Pending = pending;
        queue.Enqueue(pending);
        return pending.Completion.Task;
    }

    internal bool TryDequeue(out Pending? pending)
    {
        while (queue.TryDequeue(out pending))
        {
            if (!pending.TryStart())
            {
                Complete(pending, null, new BridgeException("cancelled", "Operation cancelled before native execution."));
                continue;
            }
            if (pending.OperationId is { } op) receipts[op].Status = "running";
            return true;
        }
        pending = null;
        return false;
    }
    internal void Complete(Pending pending, object? result, Exception? error = null)
    {
        object response;
        var outcome = "unchanged";
        if (error is null)
        {
            response = new { id = pending.Request.Id, result };
            outcome = pending.OperationId is null ? "unchanged" : "committed";
        }
        else if (error is BridgeException known)
        { response = Error(pending.Request.Id, known.Code, known.Message, known.Outcome); outcome = known.Outcome; }
        else
        { response = Error(pending.Request.Id, "host_error", error.Message, "unknown"); outcome = "unknown"; }
        if (pending.OperationId is { } op)
        {
            var receipt = receipts[op];
            receipt.Status = error is null ? "completed" : "failed";
            receipt.Outcome = outcome;
            receipt.Response = response;
            Log(new { operation_id = op, status = receipt.Status, outcome, response, at = DateTimeOffset.UtcNow });
        }
        pending.Completion.TrySetResult(response);
    }
    private static object Error(string? id, string code, string message, string outcome) => new { id, error = new { code, message, outcome } };
    private void Log(object entry)
    {
        try { lock (journalLock) File.AppendAllText(journal, JsonSerializer.Serialize(entry) + "\n"); }
        catch (IOException e) { Debug.WriteLine($"Gongke operation journal unavailable: {e.Message}"); }
        catch (UnauthorizedAccessException e) { Debug.WriteLine($"Gongke operation journal unavailable: {e.Message}"); }
    }
    public void Dispose()
    {
        stop.Cancel();
        while (queue.TryDequeue(out var pending)) Complete(pending, null, new BridgeException("host_stopping", "AutoCAD is closing.", "unchanged"));
        if (File.Exists(descriptor)) File.Delete(descriptor);
    }
    internal sealed class Pending(Request request, string? operationId)
    {
        private int state;
        internal bool TryStart() => Interlocked.CompareExchange(ref state, 1, 0) == 0;
        internal bool TryCancel() => Interlocked.CompareExchange(ref state, 2, 0) == 0;
        internal Request Request { get; } = request;
        internal string? OperationId { get; } = operationId;
        internal TaskCompletionSource<object> Completion { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    }
    private sealed class Receipt(string requestKey)
    {
        internal string RequestKey { get; } = requestKey;
        internal string Status { get; set; } = "queued";
        internal string Outcome { get; set; } = "unknown";
        internal object? Response { get; set; }
        internal Pending? Pending { get; set; }
    }
}
