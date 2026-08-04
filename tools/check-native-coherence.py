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

HERE = Path(__file__).parent

# The attribute, up to its closing parenthesis, plus everything until the opening
# parenthesis of the declaration it decorates. Both halves are needed: when
# EntryPoint is absent the symbol is the method's own name, which is how .NET
# resolves it and how most of this fleet is generated.
#
# This used to require EntryPoint. ImGui.Net declares 612 imports in one file with
# only 15 of them naming an EntryPoint, so the check reported success after looking
# at 2% of the surface -- worse than no check, because it looked like one.
DLLIMPORT = re.compile(
    r'DllImport\s*\(\s*"([^"]+)"([^)]*)\)\s*\]([^;{}]*?);', re.DOTALL)
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


def library_matches(name, filename):
    """Whether a shipped file is the library a DllImport names.

    DllImport carries the bare name -- "meshoptimizer" -- and each platform
    decorates it differently: meshoptimizer.dll, libmeshoptimizer.so,
    libmeshoptimizer.dylib.
    """
    stem = Path(filename).stem
    return stem == name or stem == f"lib{name}"


def main():
    manifest_path = Path(sys.argv[1] if len(sys.argv) > 1 else "binding.yml")
    if not manifest_path.exists():
        fail(f"{manifest_path} not found")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    project = manifest.get("package", {}).get("project")
    if not project:
        fail("manifest has no package.project")
    project_dir = Path(project).parent

    runtimes = project_dir / "runtimes"
    if not runtimes.is_dir():
        print(f"{runtimes} does not exist; this package ships no native binaries. "
              f"Nothing to check.")
        return 0

    # Every source under the package, not only the generated folders: hand-written
    # code declares P/Invokes too, and those bind just as late.
    declared = {}
    for source in project_dir.rglob("*.cs"):
        if any(part in ("bin", "obj") for part in source.parts):
            continue
        text = source.read_text(encoding="utf-8-sig", errors="replace")
        for library, attribute_args, declaration in DLLIMPORT.findall(text):
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

    print(f"Declared: " + ", ".join(
        f"{len(s)} symbol(s) from '{n}'" for n, s in sorted(declared.items())))

    problems = 0
    checked = 0
    # Which RIDs the package ships, against which ones actually got verified. The check
    # used to skip any extension it did not recognise, silently, and then report success
    # over however many were left: for JoltPhysics.NET that was seven of ten, with the
    # three .a archives -- iOS, the simulator and WebAssembly -- passing unexamined while
    # the summary read "all shipped libraries". A partial check reported as complete is
    # worse than no check, because it retires the suspicion.
    shipped_rids = {p.parent.name for p in runtimes.glob("*/native")}
    verified_rids = set()
    skipped = []

    for native in sorted(runtimes.glob("*/native/*")):
        if native.suffix.lower() not in (".dll", ".so", ".dylib", ".a") and native.suffix:
            skipped.append(str(native))
            continue
        rid = native.parent.parent.name
        for name, symbols in declared.items():
            if not library_matches(name, native.name):
                continue
            checked += 1
            missing = sorted(symbols - exported(native))
            if missing:
                problems += 1
                print(f"::error::{rid}: {len(missing)} declared symbol(s) not "
                      f"exported by {native.name}")
                for symbol in missing[:20]:
                    print(f"    {symbol}")
                if len(missing) > 20:
                    print(f"    ... and {len(missing) - 20} more")
            else:
                verified_rids.add(rid)
                print(f"  {rid}: all {len(symbols)} declared symbols present")

    if checked == 0:
        fail(f"none of the libraries under {runtimes} match the names the bindings "
             f"import ({', '.join(sorted(declared))})")

    for path in skipped:
        print(f"::warning::not a library this check can read, ignored: {path}")

    # Every RID the package ships has to have been looked at. Naming the ones that were
    # not is the whole point -- those are the platforms where a missing symbol reaches a
    # consumer, and they were invisible precisely because nothing said they were skipped.
    unverified = sorted(shipped_rids - verified_rids - {r for r in shipped_rids if problems})
    if unverified and not problems:
        fail(
            f"{len(unverified)} shipped platform(s) were not verified: "
            f"{', '.join(unverified)}. The package ships a library there and nothing "
            f"read it, so a missing symbol would reach a consumer unannounced.")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Native coherence\n\n")
            fh.write(
                f"{'Every' if not problems else 'Not every'} declared P/Invoke resolves "
                f"in {checked} shipped library file(s), covering "
                f"{len(verified_rids)} of {len(shipped_rids)} runtime identifier(s).\n")

    if problems:
        fail(f"{problems} platform(s) ship a library missing symbols the bindings "
             f"declare. Calling them would throw EntryPointNotFoundException.")

    print(f"\nAll declarations resolve on all {checked} shipped libraries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
