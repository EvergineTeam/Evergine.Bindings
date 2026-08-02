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
// assemblies. Anything it references that is missing resolves to null and is
// rendered by name, which is enough for a diff.
var paths = new List<string>(
    Directory.GetFiles(AppContext.BaseDirectory, "*.dll"));
paths.AddRange(Directory.GetFiles(
    Path.GetDirectoryName(typeof(object).Assembly.Location)!, "*.dll"));
paths.AddRange(Directory.GetFiles(
    Path.GetDirectoryName(assemblyPath)!, "*.dll"));

using var mlc = new MetadataLoadContext(
    new PathAssemblyResolver(paths.Distinct()));
var assembly = mlc.LoadFromAssemblyPath(assemblyPath);

var lines = new SortedSet<string>(StringComparer.Ordinal);

static string Name(Type? t) => t is null ? "?" : t.FullName ?? t.Name;

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
    lines.Add($"T {kind} {Name(type)} : {Name(type.BaseType)}");

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
            lines.Add($"F {Name(type)}.{f.Name} : {Name(f.FieldType)}{(f.IsStatic ? " static" : "")}");
        }
    }

    foreach (var m in type.GetMethods(Flags))
    {
        if (m.IsSpecialName) continue; // property and event accessors, rendered below
        var ps = string.Join(", ", m.GetParameters().Select(p => Name(p.ParameterType)));
        lines.Add($"M {Name(type)}.{m.Name}({ps}) : {Name(m.ReturnType)}{(m.IsStatic ? " static" : "")}");
    }

    foreach (var c in type.GetConstructors(Flags))
    {
        var ps = string.Join(", ", c.GetParameters().Select(p => Name(p.ParameterType)));
        lines.Add($"C {Name(type)}..ctor({ps})");
    }

    foreach (var p in type.GetProperties(Flags))
    {
        var acc = (p.GetGetMethod() is not null ? "get;" : "") + (p.GetSetMethod() is not null ? "set;" : "");
        lines.Add($"P {Name(type)}.{p.Name} : {Name(p.PropertyType)} {{ {acc} }}");
    }

    foreach (var e in type.GetEvents(Flags))
        lines.Add($"E {Name(type)}.{e.Name} : {Name(e.EventHandlerType)}");
}

File.WriteAllLines(outputPath, lines);
Console.WriteLine($"{lines.Count} public API entries -> {outputPath}");
return 0;
