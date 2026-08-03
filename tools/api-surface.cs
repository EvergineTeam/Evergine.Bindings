#:package System.Reflection.MetadataLoadContext@9.0.0

// Dump the public API surface of an assembly as sorted, diffable text.
//
// ApiCompat is the authority on binary compatibility, but it has one blind spot
// that matters more here than anywhere else: an enum member or constant whose
// name stays and whose *value* changes is reported as compatible, because the
// member still exists. For a binding to a native API that is the worst possible
// break -- the constant is inlined into consumer code at compile time, so an
// already-built application keeps passing the old number to the driver. No
// compile error, no crash, wrong behaviour.
//
// So every literal value is part of the surface here. A renumbering shows up as
// one removal plus one addition, and the gate refuses it.
//
// Loading is metadata-only: the assembly is never executed, and its native
// dependencies need not be present.

using System.Reflection;

if (args.Length < 2)
{
    Console.Error.WriteLine("usage: api-surface <assembly> <output>");
    return 2;
}

var assemblyPath = Path.GetFullPath(args[0]);
var outputPath = args[1];

// The dumped assembly is resolved against the running framework's reference
// assemblies plus whatever sits beside it. Searched recursively from the build output
// root rather than the single folder holding the assembly: a binding that references a
// package -- Evergine.Mathematics, for instance -- may have it one level away, and a
// reference this resolver cannot find makes reading a field's type throw.
var paths = new List<string>(
    Directory.GetFiles(AppContext.BaseDirectory, "*.dll"));
paths.AddRange(Directory.GetFiles(
    Path.GetDirectoryName(typeof(object).Assembly.Location)!, "*.dll"));

var beside = new DirectoryInfo(Path.GetDirectoryName(assemblyPath)!);
var searchRoot = beside;
for (int up = 0; up < 4 && searchRoot.Parent is not null; up++)
{
    if (searchRoot.Name is "bin" or "obj") break;
    searchRoot = searchRoot.Parent;
}
paths.AddRange(Directory.GetFiles(searchRoot.FullName, "*.dll", SearchOption.AllDirectories));

using var mlc = new MetadataLoadContext(
    new PathAssemblyResolver(paths.Distinct()));
var assembly = mlc.LoadFromAssemblyPath(assemblyPath);

var lines = new SortedSet<string>(StringComparer.Ordinal);

static string Name(Type? t) => t is null ? "?" : t.FullName ?? t.Name;

// Reading a member's type throws when the assembly it lives in cannot be resolved, and
// that killed the whole dump: one unresolvable reference and the gate learned nothing
// about the other few thousand members. ImGui.Net's bindings reference
// Evergine.Mathematics and the process aborted with SIGABRT.
//
// Degrading to a marker keeps the member in the surface, so additions and removals are
// still caught by name. Only that member's *type* becomes opaque, which is a narrow and
// stated loss rather than a total one. Counted and reported, because a dump full of
// markers is worth knowing about even though it is not worth failing over.
int unresolved = 0;
string SafeName(Func<Type?> get)
{
    try { return Name(get()); }
    catch { unresolved++; return "<unresolved>"; }
}

// The signature is decoded as a whole, so GetParameters throws before any individual
// parameter type can be inspected -- wrapping the per-parameter read was not enough and
// the process still aborted. The list has to be built inside the guard.
string SafeParams(Func<ParameterInfo[]> get)
{
    try { return string.Join(", ", get().Select(p => SafeName(() => p.ParameterType))); }
    catch { unresolved++; return "<unresolved>"; }
}

static string Literal(object? value) => value switch
{
    null => "null",
    string s => "\"" + s + "\"",
    // Invariant formatting: a runner in another locale must produce the same
    // bytes, or every diff is noise.
    IFormattable f => f.ToString(null, System.Globalization.CultureInfo.InvariantCulture),
    _ => value.ToString() ?? "?",
};

foreach (var type in assembly.GetExportedTypes().OrderBy(t => t.FullName, StringComparer.Ordinal))
{
    var kind = type.IsEnum ? "enum"
        : type.IsValueType ? "struct"
        : type.IsInterface ? "interface"
        : "class";
    lines.Add($"T {kind} {Name(type)} : {SafeName(() => type.BaseType)}");

    const BindingFlags Flags =
        BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly;

    foreach (var f in type.GetFields(Flags))
    {
        if (f.IsLiteral)
        {
            // The value is the point. See the note at the top.
            object? raw = null;
            try { raw = f.GetRawConstantValue(); } catch { }
            lines.Add($"K {Name(type)}.{f.Name} = {Literal(raw)}");
        }
        else
        {
            // Field order and type are part of the contract for a struct passed
            // to native code, but order is not observable here; the type is.
            lines.Add($"F {Name(type)}.{f.Name} : {SafeName(() => f.FieldType)}{(f.IsStatic ? " static" : "")}");
        }
    }

    foreach (var m in type.GetMethods(Flags))
    {
        if (m.IsSpecialName) continue; // property and event accessors, rendered below
        var ps = SafeParams(m.GetParameters);
        lines.Add($"M {Name(type)}.{m.Name}({ps}) : {SafeName(() => m.ReturnType)}{(m.IsStatic ? " static" : "")}");
    }

    foreach (var c in type.GetConstructors(Flags))
    {
        var ps = SafeParams(c.GetParameters);
        lines.Add($"C {Name(type)}..ctor({ps})");
    }

    foreach (var p in type.GetProperties(Flags))
    {
        var acc = (p.GetGetMethod() is not null ? "get;" : "") + (p.GetSetMethod() is not null ? "set;" : "");
        lines.Add($"P {Name(type)}.{p.Name} : {SafeName(() => p.PropertyType)} {{ {acc} }}");
    }

    foreach (var e in type.GetEvents(Flags))
        lines.Add($"E {Name(type)}.{e.Name} : {SafeName(() => e.EventHandlerType)}");
}

File.WriteAllLines(outputPath, lines);
Console.WriteLine($"{lines.Count} public API entries -> {outputPath}");
if (unresolved > 0)
    Console.WriteLine($"::warning::{unresolved} member type(s) could not be resolved and are recorded as <unresolved>. Additions and removals are still detected; those members' types are not.");
return 0;
