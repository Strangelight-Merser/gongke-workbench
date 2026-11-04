using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Gongke.AutoCAD;

// 每个 ID 一个永久占位文件和一个原子替换的状态文件。锁跨进程持有至完成，
// 不能用 PID 存活推断操作状态，也不能因为记录缺失或损坏就重新执行。
internal sealed class OperationStore
{
    private readonly string folder;
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
    internal OperationStore(string folder) { this.folder = folder; Directory.CreateDirectory(folder); }
    internal string RecordPath(string id) => Path.Combine(folder, Hash(id) + ".json");
    private string LockPath(string id) => Path.Combine(folder, Hash(id) + ".lock");
    private static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    internal static string Fingerprint(Request request)
    {
        return Hash(request.Method + "\n" + Canonical(request.Params));
    }
    private static string Canonical(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
            return "{" + string.Join(",", value.EnumerateObject().OrderBy(x => x.Name, StringComparer.Ordinal)
                .Select(x => Quote(x.Name) + ":" + Canonical(x.Value))) + "}";
        if (value.ValueKind == JsonValueKind.Array)
            return "[" + string.Join(",", value.EnumerateArray().Select(Canonical)) + "]";
        return value.ValueKind == JsonValueKind.String ? Quote(value.GetString()!) : value.GetRawText();
    }
    // 与 hosts.py 的 ensure_ascii=False 一致，包括非 BMP 路径和控制字符。
    private static string Quote(string value)
    {
        var text = new StringBuilder("\"");
        foreach (var ch in value)
            text.Append(ch switch
            {
                '"' => "\\\"", '\\' => "\\\\", '\b' => "\\b", '\f' => "\\f", '\n' => "\\n", '\r' => "\\r", '\t' => "\\t",
                _ when ch < 32 || ch is '\u0085' or '\u2028' or '\u2029' => "\\u" + ((int)ch).ToString("x4"),
                _ => ch.ToString()
            });
        return text.Append('"').ToString();
    }

    internal Lease? Begin(Request request, string session, out Record? existing)
    {
        var id = request.Params.NonEmpty("operation_id");
        FileStream handle;
        try { handle = OpenLock(id, FileMode.CreateNew); }
        catch (IOException) when (File.Exists(LockPath(id)))
        {
            existing = Get(id);
            if (existing.Fingerprint is not null && existing.Fingerprint != Fingerprint(request))
                throw new BridgeException("operation_id_conflict", "该操作 ID 已用于其他请求。");
            return null;
        }
        var record = new Record(id, session, request.Method, Fingerprint(request), request.Id, request.Params.Clone(), "queued", "unknown", null);
        try { Write(record); }
        catch { handle.Dispose(); throw; }
        existing = null;
        return new Lease(this, handle, record);
    }

    internal Record Get(string id)
    {
        // 持有锁时再读取，避免把刚入队的活跃操作误判为已退出。
        FileStream? probe = null;
        try { probe = OpenLock(id, FileMode.Open); }
        catch (FileNotFoundException) { return Record.Unknown(id); }
        catch (IOException e) when (OperatingSystem.IsWindows() ? (e.HResult & 0xffff) == 33 : File.Exists(LockPath(id))) { return Read(id); }
        using (probe)
        {
            var record = Read(id);
            return record.Status switch
            {
                "queued" => record with { Status = "interrupted_before_start", Outcome = "unchanged" },
                "running" => record with { Status = "interrupted", Outcome = "unknown" },
                _ => record
            };
        }
    }

    private FileStream OpenLock(string id, FileMode mode)
    {
        // Windows 的独占共享模式会与普通读者（例如文件扫描）冲突，不能证明操作仍在执行。
        // 用字节范围锁表示操作所有权，只有 ERROR_LOCK_VIOLATION 才表示活跃操作。
        var stream = new FileStream(LockPath(id), mode, FileAccess.ReadWrite,
            OperatingSystem.IsWindows() ? FileShare.ReadWrite : FileShare.None);
        try
        {
            if (OperatingSystem.IsWindows()) stream.Lock(0, 1);
            return stream;
        }
        catch { stream.Dispose(); throw; }
    }

    private Record Read(string id)
    {
        try
        {
            using var stream = new FileStream(RecordPath(id), FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            var record = JsonSerializer.Deserialize<Record>(stream, Json);
            return record is not null && record.OperationId == id ? record : Record.Unknown(id);
        }
        catch (FileNotFoundException) { return Record.Unknown(id); }
        catch (JsonException) { return Record.Unknown(id); }
    }

    private void Write(Record record)
    {
        var path = RecordPath(record.OperationId);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        { JsonSerializer.Serialize(stream, record, Json); stream.Flush(true); }
        File.Move(temporary, path, true);
    }

    // 副本权限来自成功持久化的原生回执；重启不依赖内存白名单。
    internal bool IsWorkingCopy(string path, string fingerprint)
    {
        foreach (var file in Directory.EnumerateFiles(folder, "*.json"))
        {
            Record? record;
            try
            {
                using var stream = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
                record = JsonSerializer.Deserialize<Record>(stream, Json);
            }
            catch (JsonException) { continue; }
            if (record?.Status != "completed" || record.Outcome != "committed" ||
                record.Method is not ("drawing.import_dxf" or "document.save_copy") || record.Response is not { } response ||
                !response.TryGetProperty("result", out var result)) continue;
            if (result.GetProperty("disk_reopen_verified").GetBoolean() && result.GetProperty("original_preserved").GetBoolean() &&
                string.Equals(result.GetProperty("path").GetString(), path, StringComparison.OrdinalIgnoreCase) &&
                result.GetProperty("native_fingerprint").GetString() == fingerprint) return true;
        }
        return false;
    }

    internal sealed record Record(string OperationId, string? SessionId, string? Method, string? Fingerprint,
        string? RequestId, JsonElement? Params, string Status, string Outcome, JsonElement? Response)
    {
        internal static Record Unknown(string id) => new(id, null, null, null, null, null, "unknown", "unknown", null);
        internal object Wire() => new { operation_id = OperationId, session_id = SessionId, method = Method,
            fingerprint = Fingerprint, request_id = RequestId, @params = Params, status = Status, outcome = Outcome, response = Response };
    }
    internal sealed class Lease(OperationStore store, FileStream handle, Record record) : IDisposable
    {
        internal Record Current { get; private set; } = record;
        internal void Update(string status, string outcome, object? response = null)
        {
            var next = Current with { Status = status, Outcome = outcome,
                Response = response is null ? null : JsonSerializer.SerializeToElement(response) };
            store.Write(next);
            Current = next;
        }
        public void Dispose() => handle.Dispose();
    }
}
