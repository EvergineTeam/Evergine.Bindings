"""Check that every P/Invoke the managed binding declares exists in the native
libraries the package ships, on every platform it ships them for.

This is the one failure a binding that carries native binaries cannot afford and
that nothing else catches. P/Invoke binds late: a managed declaration naming a
symbol the library does not export compiles cleanly, passes CI, packs, publishes,
and throws EntryPointNotFoundException the first time a consumer calls it. The
header and the libraries drifting apart by one release is enough to cause it.

Deliberately a static check rather than a smoke test. A smoke test calls the two
or three functions someone thought to write down, on whichever platform CI runs;
this compares every declaration against every shipped library, from one machine.
It says nothing about whether a function behaves correctly -- only that calling it
will not fail to bind, which is the part that fails silently.

Usage: check-native-coherence.py [manifest]
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

from native_paths import shipped_natives

HERE = Path(__file__).parent

# The attribute, up to its closing parenthesis, plus everything until the opening
# parenthesis of the declaration it decorates. Both halves are needed: when
# EntryPoint is absent the symbol is the method's own name, which is how .NET
# resolves it and how most of this fleet is generated.
#
# This used to require EntryPoint. ImGui.Net declares 612 imports in one file with
# only 15 of them naming an EntryPoint, so the check reported success after looking
# at 2% of the surface -- worse than no check, because it looked like one.
#
# The library name is not always a literal. Vuforia.NET generates
# `[DllImport(Native.Dll, ...)]`, where Native.Dll is a const chosen by the target -- the
# library name on Android, "__Internal" on iOS, because there the library is linked
# statically into the app. Requiring a quoted string meant all 495 of its declarations
# matched nothing at all, and the check died claiming the bindings had not been generated.
# Now the first argument may be a literal or an expression; when it is an expression the
# library is unknown, and the symbol is required to resolve in *some* shipped library
# rather than in a file whose name we cannot predict.
DLLIMPORT = re.compile(
    r'DllImport\s*\(\s*(?:"(?P<literal>[^"]+)"|(?P<expression>[A-Za-z_][\w.]*))'
    r'(?P<args>[^)]*)\)\s*\](?P<declaration>[^;{}]*?);', re.DOTALL)
ENTRYPOINT = re.compile(r'EntryPoint\s*=\s*"([^"]+)"')
# Attribute blocks sitting between the DllImport and the name, or on parameters:
# [return:MarshalAs(UnmanagedType.I1)] and [MarshalAs(...)] string arg. Stripped
# first, because their own parenthesis comes before the parameter list and a naive
# "identifier before the first (" reads them as the imported symbol -- 163 of
# ImGui.Net's 612 imports resolved to "MarshalAs" before this.
ATTRIBUTE = re.compile(r'\[[^\]]*\]')
# First identifier that opens a parameter list: the method name.
METHOD = re.compile(r'(\w+)\s*\(')


def fail(message):
    print(f"::error::{message}")
    sys.exit(1)


def exported(library):
    """Exported symbols of one library, via the format-aware dumper."""
    result = subprocess.run(
        [sys.executable, str(HERE / "dump-exports.py"), str(library)],
        capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"could not read exports from {library}: {result.stderr.strip()}")
    return set(result.stdout.split())


# library_matches used to live here, pairing a DllImport name with the shipped file it
# referred to -- "meshoptimizer" against meshoptimizer.dll and libmeshoptimizer.so. It is
# gone because nothing pairs them any more: the comparison is against the union of every
# shipped library, so which file a name refers to stopped being a question this has to
# answer. It could not have answered it for Apple targets anyway, where the name is
# "__Internal" and refers to the consuming application rather than to anything we ship.


def main():
    manifest_path = Path(sys.argv[1] if len(sys.argv) > 1 else "binding.yml")
    if not manifest_path.exists():
        fail(f"{manifest_path} not found")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    project = manifest.get("package", {}).get("project")
    if not project:
        fail("manifest has no package.project")
    project_dir = Path(project).parent

    natives, path_problems = shipped_natives(manifest, project_dir)
    if not natives and not path_problems:
        print(f"{project_dir} ships no native binaries. Nothing to check.")
        return 0

    # Every source under the package, not only the generated folders: hand-written
    # code declares P/Invokes too, and those bind just as late.
    declared = {}
    for source in project_dir.rglob("*.cs"):
        if any(part in ("bin", "obj") for part in source.parts):
            continue
        text = source.read_text(encoding="utf-8-sig", errors="replace")
        for match in DLLIMPORT.finditer(text):
            # None when the name came from an expression rather than a literal. Kept as a
            # distinct key so the report still separates one library from another where it
            # can, instead of pooling everything the moment one declaration is indirect.
            library = match.group("literal")
            attribute_args = match.group("args")
            declaration = match.group("declaration")
            entry = ENTRYPOINT.search(attribute_args)
            if entry:
                symbol = entry.group(1)
            else:
                name = METHOD.search(ATTRIBUTE.sub(" ", declaration))
                if not name:
                    # A DllImport whose symbol cannot be determined is worse than one
                    # that is wrong, because it would be silently dropped from the
                    # comparison and the check would still pass.
                    fail(f"{source}: cannot read the imported symbol from "
                         f"'{declaration.strip()[-60:]}'")
                symbol = name.group(1)
            declared.setdefault(library, set()).add(symbol)

    if not declared:
        fail(f"no DllImport declarations found under {project_dir} -- either the "
             f"bindings were not generated or this check is looking in the wrong place")

    print("Declared: " + ", ".join(
        f"{len(s)} symbol(s) from '{n or 'a library named by an expression'}'"
        for n, s in sorted(declared.items(), key=lambda kv: kv[0] or "")))

    # Read each library once, and remember which RID it belonged to. Read once because the
    # dumper shells out and these files run to tens of megabytes; remembered per RID because
    # "which platform is missing this symbol" is the only useful thing to say about a failure.
    exports_by_rid = {}
    # Built from what resolved *and* from what did not, which is the whole point. Taking it
    # from the resolved entries alone would mean a platform whose only file cannot be read
    # never enters the set, so the "was every platform read" check below could not miss it --
    # it would not know the platform existed. That is the same shape as the fault this check
    # was written for, reintroduced one level up.
    shipped_rids = {rid for rid, _ in natives} | {rid for rid, _ in path_problems if rid != "?"}
    for rid, path in natives:
        symbols = exported(path)
        exports_by_rid.setdefault(rid, set()).update(symbols)
        print(f"  {rid}: {path.name} exports {len(symbols)} symbol(s)")

    # Every platform the package ships has to have been read. This is the property that
    # caught JoltPhysics.NET shipping ten libraries with three of them -- the iOS, simulator
    # and WebAssembly archives -- passing unexamined while the summary read "all shipped
    # libraries"; a partial check reported as complete is worse than no check, because it
    # retires the suspicion. It is kept separate from the symbol comparison below on purpose:
    # relaxing that comparison must not be able to take this guarantee with it.
    unread = sorted(rid for rid in shipped_rids if not exports_by_rid.get(rid))
    for rid, reason in path_problems:
        print(f"::warning::{rid}: {reason}")
    if unread:
        fail(f"{len(unread)} shipped platform(s) could not be read: {', '.join(unread)}. "
             f"The package ships a library there and nothing looked inside it, so a missing "
             f"symbol would reach a consumer unannounced.")
    declared_problems = [p for p in path_problems if p[1].startswith("declared ")]
    if declared_problems:
        fail(f"{len(declared_problems)} path(s) in package.natives do not resolve. Somebody "
             f"wrote them down, so this is the manifest being wrong rather than something to "
             f"skip.")

    # A symbol has to resolve in at least one shipped library, not in every one.
    #
    # A package whose managed surface is the union of several platforms cannot satisfy
    # "every symbol in every library" and should not be asked to. Vuforia.NET declares four
    # ARKit functions and three ARCore ones; the iOS framework exports the first set and not
    # the second, the Android library the other way round, and both are correct. Measured:
    # 495 declarations, 3 absent from iOS, 4 absent from Android, none absent from both.
    #
    # What this gives up, stated rather than discovered later: a function that ought to exist
    # on both platforms and only exists on one still passes. Catching that would mean
    # teaching this check which platform each declaration belongs to -- reading the #if
    # guards in the generated source and mapping target frameworks to RIDs -- which couples
    # it to how one generator happens to emit guards.
    everywhere = set().union(*exports_by_rid.values()) if exports_by_rid else set()
    problems = 0
    for name, symbols in sorted(declared.items(), key=lambda kv: kv[0] or ""):
        missing = sorted(symbols - everywhere)
        label = name or "the imports"
        if missing:
            problems += 1
            print(f"::error::{len(missing)} symbol(s) declared by {label} are exported by "
                  f"no shipped library")
            for symbol in missing[:20]:
                print(f"    {symbol}")
            if len(missing) > 20:
                print(f"    ... and {len(missing) - 20} more")
        else:
            print(f"  {label}: all {len(symbols)} declared symbols resolve somewhere")

    # Reported without failing: this is the per-platform detail the union deliberately
    # tolerates, and it is worth seeing rather than hiding. A number that grows unexpectedly
    # after an upstream refresh is the signal.
    for rid in sorted(shipped_rids):
        elsewhere = {s for symbols in declared.values() for s in symbols} - exports_by_rid[rid]
        if elsewhere:
            print(f"  {rid}: {len(elsewhere)} declared symbol(s) live on another platform")

    total_declared = len({s for symbols in declared.values() for s in symbols})

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Native coherence\n\n")
            fh.write(
                f"{'Every' if not problems else 'Not every'} one of {total_declared} declared "
                f"P/Invoke(s) resolves in the {len(natives)} shipped library file(s), across "
                f"{len(shipped_rids)} runtime identifier(s), all of them read.\n")

    if problems:
        fail(f"{problems} group(s) of declarations name symbols no shipped library exports. "
             f"Calling them would throw EntryPointNotFoundException.")

    print(f"\nAll {total_declared} declarations resolve, across {len(shipped_rids)} "
          f"platform(s): {', '.join(sorted(shipped_rids))}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
