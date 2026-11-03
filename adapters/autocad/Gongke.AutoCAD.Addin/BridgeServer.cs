using System.Collections.Concurrent;
using System.IO.Pipes;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Gongke.AutoCAD;

internal sealed class BridgeServer : IDisposable
{
    private readonly CancellationTokenSource stop = new();
    private readonly ConcurrentQueue<Pending> queue = new();
    private readonly Dictionary<string, Pending> pendingOperations = new();
    private readonly object gate = new();
    private bool disposed;
    private Task? listener;
    private readonly string token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
    private readonly string pipeName = $"gongke-autocad-{Environment.ProcessId}";
    private readonly string session = Guid.NewGuid().ToString("N");
    private readonly string folder;
    private readonly string descriptor;
    internal OperationStore Operations { get; }
    internal static readonly HashSet<string> Mutations = ["drawing.edit_text", "drawing.move_dimension_text", "drawing.import_dxf", "document.save_copy", "document.open", "document.select"];
    internal string Session => session;
    internal int PendingCount => queue.Count;

    internal BridgeServer(string? discoveryFolder = null)
    {
        folder = discoveryFolder ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Gongke", "hosts");
        Directory.CreateDirectory(folder);
        descriptor = Path.Combine(folder, $"autocad-{Environment.ProcessId}.json");
        Operations = new OperationStore(Path.Combine(folder, "autocad-operations"));
    }

    internal void Start()
    {
        File.WriteAllText(descriptor, JsonSerializer.Serialize(new {
            host_id = $"autocad-{session}", host = "autocad", instance_id = session, pid = Environment.ProcessId,
            transport = "named_pipe", pipe_name = pipeName, token, protocol_version = 1,
            started_at = DateTimeOffset.UtcNow, validation_level = "sdk_compiled_host_unverified"
        }));
        listener = Task.Run(Listen);
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
                System.Diagnostics.Trace.TraceError($"AutoCAD 管道错误：{e}");
                try { await Task.Delay(1000, stop.Token).ConfigureAwait(false); }
                catch (OperationCanceledException) when (stop.IsCancellationRequested) { break; }
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
                    catch (Exception e) when (e is IOException or UnauthorizedAccessException)
                    { response = Error(id, "operation_store_unavailable", e.Message, "unknown"); }
                    catch (Exception e) when (e is JsonException or InvalidOperationException or KeyNotFoundException or FormatException)
                    { response = Error(id, "invalid_request", e.Message, "unchanged"); }
                    await writer.WriteLineAsync(JsonSerializer.Serialize(response));
                }
            }
            catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
            catch (IOException) { /* Client disconnect does not cancel or replay a host operation. */ }
            catch (Exception e)
            {
                System.Diagnostics.Trace.TraceError($"AutoCAD 管道错误：{e}");
            }
        }
    }

    private Task<object> Submit(Request request)
    {
        lock (gate)
        {
            if (disposed) throw new BridgeException("host_stopping", "AutoCAD 正在关闭。");
            if (request.Method == "operation.status")
                return Task.FromResult<object>(new { id = request.Id, result = Operations.Get(request.Params.NonEmpty("operation_id")).Wire() });
            if (request.Method == "operation.cancel")
            {
                var operationId = request.Params.NonEmpty("operation_id");
                var cancelled = pendingOperations.TryGetValue(operationId, out var item) && !item.Started;
                if (cancelled)
                    Complete(item!, null, new BridgeException("cancelled", "操作在执行前取消。"));
                var state = Operations.Get(operationId);
                return Task.FromResult<object>(new { id = request.Id, result = new { operation_id = operationId,
                    cancelled, status = state.Status, outcome = state.Outcome } });
            }
            OperationStore.Lease? lease = null;
            if (Mutations.Contains(request.Method))
            {
                lease = Operations.Begin(request, session, out var existing);
                if (lease is null)
                    return Task.FromResult<object>(new { id = request.Id, result = existing!.Wire() });
            }
            var pending = new Pending(request, lease);
            if (lease is not null) pendingOperations.Add(lease.Current.OperationId, pending);
            queue.Enqueue(pending);
            return pending.Completion.Task;
        }
    }

    internal bool TryDequeue(out Pending? pending)
    {
        lock (gate)
        {
            while (queue.TryDequeue(out pending))
            {
                if (pending.Completion.Task.IsCompleted) continue;
                try { pending.Lease?.Update("running", "unknown"); }
                catch (Exception e) when (e is IOException or UnauthorizedAccessException)
                {
                    // 执行屏障未落盘，绝不调用原生 API。保留旧记录和占位供后续查询。
                    FinishUnavailable(pending, e, "unchanged");
                    continue;
                }
                pending.Started = true;
                return true;
            }
            pending = null;
            return false;
        }
    }
    internal void Complete(Pending pending, object? result, Exception? error = null)
    {
        lock (gate)
        {
            if (pending.Completion.Task.IsCompleted) return;
            var outcome = error is null ? (pending.Lease is null ? "unchanged" : "committed")
                : error is BridgeException known ? known.Outcome : "unknown";
            object response = error is null ? new { id = pending.Request.Id, result }
                : Error(pending.Request.Id, error is BridgeException bridge ? bridge.Code : "host_error", error.Message, outcome);
            try
            {
                pending.Lease?.Update(error is null ? "completed" : !pending.Started ? "cancelled_before_start" : "failed", outcome, response);
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException)
            {
                // 原生结果和回执不是同一事务；完成记录失败必须对客户端可见。
                FinishUnavailable(pending, e, pending.Started ? "unknown" : "unchanged");
                return;
            }
            Release(pending);
            pending.Completion.TrySetResult(response);
        }
    }
    private void FinishUnavailable(Pending pending, Exception error, string outcome)
    {
        Release(pending);
        pending.Completion.TrySetResult(Error(pending.Request.Id, "operation_store_unavailable", error.Message, outcome));
    }
    private void Release(Pending pending)
    {
        if (pending.Lease is not { } lease) return;
        pendingOperations.Remove(lease.Current.OperationId);
        lease.Dispose();
    }
    private static object Error(string? id, string code, string message, string outcome) => new { id, error = new { code, message, outcome } };
    public void Dispose()
    {
        lock (gate)
        {
            if (disposed) return;
            disposed = true;
            stop.Cancel();
            while (queue.TryDequeue(out var pending))
                Complete(pending, null, new BridgeException("host_stopping", "AutoCAD 正在关闭。"));
            foreach (var pending in pendingOperations.Values.ToArray())
                Complete(pending, null, new BridgeException("host_stopping", "原生操作执行中退出，需读回确认。", "unknown"));
            if (File.Exists(descriptor)) File.Delete(descriptor);
        }
        listener?.GetAwaiter().GetResult();
    }
    internal sealed class Pending(Request request, OperationStore.Lease? lease)
    {
        internal bool Started { get; set; }
        internal Request Request { get; } = request;
        internal OperationStore.Lease? Lease { get; } = lease;
        internal TaskCompletionSource<object> Completion { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    }
}
