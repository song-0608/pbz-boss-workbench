// Offline character conversion only. Never starts or writes to the game.
using System.Text.Json;
using CUE4Parse.FileProvider;
using CUE4Parse.Encryption.Aes;
using CUE4Parse.MappingsProvider.Usmap;
using CUE4Parse.UE4.Objects.Core.Misc;
using CUE4Parse.UE4.Versions;
using CUE4Parse.Compression;
using CUE4Parse_Conversion;
using CUE4Parse_Conversion.Options;

if (args.Length != 4)
    throw new ArgumentException("Expected: paks-directory local-crypto-file job-json new-output-directory");
var paks = Path.GetFullPath(args[0]);
var output = Path.GetFullPath(args[3]);
if (Directory.Exists(output) && Directory.EnumerateFileSystemEntries(output).Any())
    throw new IOException("Preserve existing conversion output; choose a new output directory");
if (!Directory.Exists(paks) || output.StartsWith(paks + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
    || string.Equals(output, paks, StringComparison.OrdinalIgnoreCase))
    throw new ArgumentException("A separate existing game package source and new output directory are required");
using var job = JsonDocument.Parse(File.ReadAllText(args[2]));
var paths = job.RootElement.GetProperty("packages").EnumerateArray().Select(v => v.GetString()!).ToArray();
if (paths.Length is < 1 or > 64 || paths.Any(p => string.IsNullOrWhiteSpace(p)
    || p.Contains("..") || p.Contains(':') || p.Contains('\\') || !p.EndsWith(".uasset", StringComparison.OrdinalIgnoreCase)))
    throw new ArgumentException("Bounded explicit asset paths required");
var mode = job.RootElement.GetProperty("mode").GetString();
if (mode is not ("inspect" or "export")) throw new ArgumentException("Unknown job mode");
var gameName = job.RootElement.TryGetProperty("game", out var gameValue) ? gameValue.GetString()! : "GAME_UE5_7";
var game = Enum.Parse<EGame>(gameName);
// Keys are read from a local file, never from command arguments or printed.
using var crypto = JsonDocument.Parse(File.ReadAllText(args[1]));
var keyBytes = Convert.FromBase64String(crypto.RootElement.GetProperty("EncryptionKey").GetProperty("Key").GetString()!);
if (keyBytes.Length != 32) throw new ArgumentException("Expected a local AES-256 asset key");
var keyHex = Convert.ToHexString(keyBytes);
string Redact(string message) => message.Replace(keyHex, "[local asset key]", StringComparison.OrdinalIgnoreCase)
    .Replace(Convert.ToBase64String(keyBytes), "[local asset key]", StringComparison.Ordinal);
Directory.CreateDirectory(output);
var codecPath = Path.Combine(AppContext.BaseDirectory, "oo2core_9_win64.dll");
if (!File.Exists(codecPath)) throw new FileNotFoundException("Build the local UE Oodle SDK codec before conversion", codecPath);
OodleHelper.Initialize(codecPath);
Console.WriteLine("Local installed UE codec initialized");
using var provider = new DefaultFileProvider(paks, SearchOption.TopDirectoryOnly, new VersionContainer(game), StringComparer.OrdinalIgnoreCase);
provider.Initialize();
provider.SubmitKey(new FGuid(), new FAesKey(keyHex));
Console.WriteLine("Mounted files: " + provider.Files.Count);
if (job.RootElement.TryGetProperty("usmap", out var mapping) && !string.IsNullOrWhiteSpace(mapping.GetString()))
    provider.MappingsContainer = new FileUsmapTypeMappingsProvider(mapping.GetString()!);
var results = new List<object>();
var failed = 0;
foreach (var path in paths)
{
    var row = new Dictionary<string, object?> { ["package"] = path, ["exported"] = false };
    try
    {
        var package = provider.LoadPackage(path);
        var exports = package.GetExports().ToArray();
        row["exports"] = exports.Select(v => new { name = v.Name, type = v.ExportType }).ToArray();
        if (mode == "export")
        {
            var meshFormat = job.RootElement.TryGetProperty("mesh_format", out var meshValue) ? meshValue.GetString()! : "ActorX";
            var options = new ExportOptions(meshFormat: Enum.Parse<EMeshFormat>(meshFormat, true),
                meshQuality: EMeshQuality.Highest,
                exportMaterials: job.RootElement.TryGetProperty("export_materials", out var materialValue) && materialValue.GetBoolean());
            var files = new List<string>();
            foreach (var asset in exports.Where(v => v.ExportType is "SkeletalMesh" or "Skeleton" or "AnimSequence" or "StaticMesh"))
            {
                var session = new ExportSession(null);
                session.Add(asset);
                var converted = await session.RunAsync(output, options, null, CancellationToken.None);
                foreach (var conversion in converted)
                {
                    if (!conversion.Success) throw conversion.Error ?? new InvalidOperationException("Asset conversion failed");
                    files.AddRange(conversion.DiskFilePaths ?? Array.Empty<string>());
                }
            }
            row["files"] = files;
            row["exported"] = files.Count > 0;
            if (files.Count == 0) throw new InvalidOperationException("No supported geometry or animation was exported");
        }
        row["passed"] = true;
    }
    catch (Exception error)
    {
        row["passed"] = false;
        row["error_type"] = error.GetType().FullName;
        row["error"] = Redact(error.ToString());
        failed++;
    }
    results.Add(row);
    Console.WriteLine(JsonSerializer.Serialize(new { package = path, passed = row["passed"], exported = row["exported"] }));
}
var report = new {
    schema = 1, mode, game = gameName, mounted_files = provider.Files.Count,
    supported_mesh_formats = Enum.GetNames<EMeshFormat>(),
    packages = results, passed = failed == 0, game_started = false, imported_to_editor = false
};
using (var resultFile = new FileStream(Path.Combine(output, "conversion-result.json"), FileMode.CreateNew))
    JsonSerializer.Serialize(resultFile, report, new JsonSerializerOptions { WriteIndented = true });
return failed == 0 ? 0 : 1;
