// Bounded offline native combat Blueprint script read. No editor/game process access.
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using CUE4Parse.FileProvider;
using CUE4Parse.Encryption.Aes;
using CUE4Parse.MappingsProvider.Usmap;
using CUE4Parse.UE4.Objects.Core.Misc;
using CUE4Parse.UE4.Objects.UObject;
using CUE4Parse.UE4.Versions;
using CUE4Parse.Compression;

if (args.Length != 4) throw new ArgumentException("Expected paks, private crypto file, job, new output");
string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
var paks=Path.GetFullPath(args[0]);var output=Path.GetFullPath(args[3]);
if (!Directory.Exists(paks) || Directory.Exists(output)
    || string.Equals(output,paks,StringComparison.OrdinalIgnoreCase)
    || output.StartsWith(paks+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))
    throw new ArgumentException("New output outside the existing package source required");
var jobBytes=File.ReadAllBytes(args[2]);using var job=JsonDocument.Parse(jobBytes);
var paths=job.RootElement.GetProperty("packages").EnumerateArray().Select(x=>x.GetString()!).ToArray();
if (paths.Length is < 1 or > 8 || paths.Any(p=>string.IsNullOrWhiteSpace(p)||p.Contains("..")
    ||p.Contains(':')||p.Contains('\\')||!p.EndsWith(".uasset",StringComparison.Ordinal)
    ||!(p.StartsWith("ProjectPBZ/Plugins/Secret/PBZDeflectSystem/",StringComparison.Ordinal)
        ||p=="ProjectPBZ/Plugins/Secret/PBZCombatAsset/Content/Prototypes/Actions/GAAction_WeaponParticle_BlueRedEye.uasset")))
    throw new ArgumentException("Only explicit bounded native defense/cue packages accepted");
var mapping=job.RootElement.GetProperty("usmap").GetString()!;
if (!File.Exists(mapping)) throw new ArgumentException("Exact existing local mapping required");
using var crypto=JsonDocument.Parse(File.ReadAllBytes(args[1]));
var keyBytes=Convert.FromBase64String(crypto.RootElement.GetProperty("EncryptionKey").GetProperty("Key").GetString()!);
if(keyBytes.Length!=32)throw new ArgumentException("Local AES-256 asset key required");
var keyHex=Convert.ToHexString(keyBytes);
string Redact(string message)=>message.Replace(keyHex,"[local key]",StringComparison.OrdinalIgnoreCase)
    .Replace(Convert.ToBase64String(keyBytes),"[local key]",StringComparison.Ordinal);
OodleHelper.Initialize(Path.Combine(AppContext.BaseDirectory,"oo2core_9_win64.dll"));
using var provider=new DefaultFileProvider(paks,SearchOption.TopDirectoryOnly,
    new VersionContainer(EGame.GAME_UE5_7),StringComparer.OrdinalIgnoreCase);
provider.ReadScriptData=true; // Default declaration export skips Blueprint scripts.
provider.Initialize();provider.SubmitKey(new FGuid(),new FAesKey(keyHex));
provider.MappingsContainer=new FileUsmapTypeMappingsProvider(mapping);
Directory.CreateDirectory(output);var rows=new List<object>();var failures=0;
foreach(var path in paths){
    var row=new Dictionary<string,object?>{["package"]=path};
    try{
        var exports=provider.LoadPackage(path).GetExports().ToArray();
        var functions=exports.OfType<UFunction>().ToArray();
        if(functions.Length==0||functions.Length>256)throw new InvalidDataException("Bounded Blueprint functions required");
        // CUE4Parse may retain a partial expression list after parse failure.
        // Require an explicit EndOfScript for every nonempty function.
        var scripts=functions.Select(f=>new{name=f.Name,statements=f.ScriptBytecode?.Select(e=>new{
                offset=e.StatementIndex,expression=e}).ToArray(),
            complete=f.ScriptBytecode is {Length:>0} && f.ScriptBytecode[^1].Token.ToString()=="EX_EndOfScript"}).ToArray();
        var text=Newtonsoft.Json.JsonConvert.SerializeObject(scripts,Newtonsoft.Json.Formatting.Indented,
            new Newtonsoft.Json.JsonSerializerSettings{MaxDepth=128,ReferenceLoopHandling=Newtonsoft.Json.ReferenceLoopHandling.Error});
        var bytes=Encoding.UTF8.GetBytes(text);
        if(bytes.Length>16*1024*1024)throw new InvalidDataException("Script metadata exceeds bound");
        var name=$"script-{rows.Count:D2}.json";
        using(var file=new FileStream(Path.Combine(output,name),FileMode.CreateNew))file.Write(bytes);
        var complete=scripts.All(s=>s.complete);
        row["script_file"]=name;row["sha256"]=Hash(bytes);row["functions"]=scripts.Length;
        row["complete_functions"]=scripts.Count(s=>s.complete);row["passed"]=complete;
        if(!complete)failures++;
    }catch(Exception error){row["passed"]=false;row["error"]=Redact(error.ToString());failures++;}
    rows.Add(row);Console.WriteLine(JsonSerializer.Serialize(new{package=path,passed=row["passed"]}));
}
var report=new{schema=1,kind="offline_native_combat_blueprint_scripts",job_sha256=Hash(jobBytes),
    mapping_sha256=Hash(File.ReadAllBytes(mapping)),tool_sha256=Hash(File.ReadAllBytes(
        System.Reflection.Assembly.GetExecutingAssembly().Location)),packages=rows,passed=failures==0,
    game_started=false,installed=false,runtime_behavior_verified=false};
using(var file=new FileStream(Path.Combine(output,"result.json"),FileMode.CreateNew))
    JsonSerializer.Serialize(file,report,new JsonSerializerOptions{WriteIndented=true});
return failures==0?0:1;
