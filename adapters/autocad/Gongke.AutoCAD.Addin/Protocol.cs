using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Gongke.AutoCAD;

public sealed class BridgeException(string code, string message, string outcome = "unchanged") : Exception(message)
{
    public string Code { get; } = code;
    public string Outcome { get; } = outcome;
}

public sealed record Request(string Id, string Method, JsonElement Params)
{
    public static Request Parse(string line, string token)
    {
        if (line.Length > 1_048_576) throw new BridgeException("request_too_large", "Request exceeds 1 MiB.");
        using var json = JsonDocument.Parse(line);
        var root = json.RootElement;
        var supplied = root.GetProperty("token").GetString() ?? "";
        if (!CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(supplied), Encoding.UTF8.GetBytes(token)))
            throw new BridgeException("unauthorized", "Invalid local connection token.");
        var id = root.GetProperty("id").GetString();
        var method = root.GetProperty("method").GetString();
        if (string.IsNullOrWhiteSpace(id) || string.IsNullOrWhiteSpace(method))
            throw new BridgeException("invalid_request", "id and method must be nonempty strings.");
        return new Request(id, method, root.TryGetProperty("params", out var p) ? p.Clone() : JsonSerializer.SerializeToElement(new { }));
    }
}

public static class Parameters
{
    public static string Text(this JsonElement p, string name)
    {
        if (!p.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.String)
            throw new BridgeException("invalid_parameter", $"{name} must be a string.");
        return value.GetString()!;
    }
    public static string NonEmpty(this JsonElement p, string name)
    {
        var value = p.Text(name);
        if (string.IsNullOrWhiteSpace(value)) throw new BridgeException("invalid_parameter", $"{name} cannot be empty.");
        return value;
    }
    public static long Integer(this JsonElement p, string name)
    {
        if (!p.TryGetProperty(name, out var value) || !value.TryGetInt64(out var result))
            throw new BridgeException("invalid_parameter", $"{name} must be an integer.");
        return result;
    }
    public static double[] Point(this JsonElement p, string name)
    {
        if (!p.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.Array || value.GetArrayLength() != 3)
            throw new BridgeException("invalid_parameter", $"{name} must contain three coordinates.");
        var point = value.EnumerateArray().Select(x => x.GetDouble()).ToArray();
        if (point.Any(x => !double.IsFinite(x))) throw new BridgeException("invalid_parameter", "Coordinates must be finite.");
        return point;
    }
}

public static class FilePolicy
{
    public static string Existing(string value, string extension)
    {
        if (!Path.IsPathFullyQualified(value) || !string.Equals(Path.GetExtension(value), extension, StringComparison.OrdinalIgnoreCase))
            throw new BridgeException("invalid_path", $"An absolute {extension} path is required.");
        var path = Path.GetFullPath(value);
        if (!File.Exists(path)) throw new BridgeException("missing_file", "The source file does not exist.");
        return path;
    }
    public static string NewDwg(string value)
    {
        if (!Path.IsPathFullyQualified(value) || !string.Equals(Path.GetExtension(value), ".dwg", StringComparison.OrdinalIgnoreCase))
            throw new BridgeException("invalid_path", "An absolute new .dwg path is required.");
        var path = Path.GetFullPath(value);
        if (!Directory.Exists(Path.GetDirectoryName(path))) throw new BridgeException("missing_directory", "The destination folder does not exist.");
        if (File.Exists(path) || Directory.Exists(path)) throw new BridgeException("destination_exists", "Existing files are never overwritten.");
        return path;
    }
    // Save to a unique staging file, then atomic no-overwrite move, so a race cannot replace a user file.
    public static string Staging(string target) => Path.Combine(Path.GetDirectoryName(target)!, $".gongke-{Guid.NewGuid():N}.dwg");
    public static void Publish(string staging, string target) => File.Move(staging, target, false);
}
