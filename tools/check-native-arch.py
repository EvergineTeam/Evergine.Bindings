"""Check that each shipped native library is built for the architecture its RID promises.

A runtimes folder is a promise: .NET picks the library under the RID matching the host,
so runtimes/osx-x64 must hold an x86_64 binary. Nothing verifies that. The symbol check
next door does not: every symbol can be present in a library built for the wrong
machine, so it reports success while the package cannot load at all.

Found the hard way in ImGui.Net, where runtimes/osx-x64 held an arm64 dylib -- shipped,
published, and unloadable on every Intel Mac. The cause was a comma in the build
script, and the only reason it surfaced was a linker complaining about something else.

Reads the machine field out of the binary itself: PE, ELF, Mach-O, and ar archives by
looking at their first member, which covers the static libraries shipped for wasm and
iOS.

Usage: check-native-arch.py [manifest]
"""

import os
import struct
import sys
from pathlib import Path

import yaml

from native_paths import shipped_natives

# What each RID promises. Names are normalised, so "x86_64" and "amd64" agree.
EXPECTED = {
    "win-x64": "x86_64", "win-x86": "i386", "win-arm64": "arm64",
    "linux-x64": "x86_64", "linux-arm64": "arm64", "linux-arm": "arm",
    "osx-x64": "x86_64", "osx-arm64": "arm64",
    "android-x64": "x86_64", "android-arm64": "arm64", "android-arm": "arm",
    "ios-arm64": "arm64", "iossimulator-arm64": "arm64",
    "browser-wasm": "wasm",
}

PE_MACHINE = {0x8664: "x86_64", 0x014C: "i386", 0xAA64: "arm64", 0x01C4: "arm"}
ELF_MACHINE = {0x3E: "x86_64", 0x03: "i386", 0xB7: "arm64", 0x28: "arm"}
MACHO_CPU = {0x01000007: "x86_64", 0x00000007: "i386",
             0x0100000C: "arm64", 0x0000000C: "arm"}


def fail(message):
    print(f"::error::{message}")
    sys.exit(1)


def pe_arch(data):
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[offset:offset + 4] != b"PE\0\0":
        return None
    return PE_MACHINE.get(struct.unpack_from("<H", data, offset + 4)[0])


def elf_arch(data):
    little = data[5] == 1
    fmt = "<H" if little else ">H"
    return ELF_MACHINE.get(struct.unpack_from(fmt, data, 18)[0])


def macho_arch(data):
    magic = struct.unpack_from(">I", data, 0)[0]

    # A universal binary is a table of thin ones, and the field at offset 4 is the count of
    # architectures rather than a cputype. Read as a cputype it means nothing, MACHO_CPU
    # returns None, and the caller reports the file as unreadable and fails -- so a fat
    # binary looked like a corrupt one. Apple ships these routinely, and while every Apple
    # payload in this fleet happens to be thin today, that is luck rather than a property.
    #
    # A fat file is accepted when its members agree on an architecture, which is what a
    # single-slice fat wrapper is; when they genuinely differ the RID cannot describe it and
    # saying so is the honest answer.
    if magic in (0xCAFEBABE, 0xBEBAFECA, 0xCAFEBABF):
        wide = magic == 0xCAFEBABF
        fmt = ">I" if magic in (0xCAFEBABE, 0xCAFEBABF) else "<I"
        count = struct.unpack_from(fmt, data, 4)[0]
        stride = 32 if wide else 20
        found = set()
        for index in range(count):
            entry = 8 + index * stride
            if entry + 8 > len(data):
                return None
            found.add(MACHO_CPU.get(struct.unpack_from(fmt, data, entry)[0]))
        found.discard(None)
        return found.pop() if len(found) == 1 else None

    fmt = "<I" if magic in (0xCEFAEDFE, 0xCFFAEDFE) else ">I"
    return MACHO_CPU.get(struct.unpack_from(fmt, data, 4)[0])


def ar_first_member(data):
    """First member of an ar archive, which is enough to read the machine from.

    Every object in one of these was produced by the same compiler invocation, so the
    first is representative. Used for the static libraries shipped for wasm and iOS.
    """
    offset = 8
    while offset + 60 <= len(data):
        raw_name = data[offset:offset + 16].decode("latin1").strip()
        try:
            size = int(data[offset + 48:offset + 58].decode("latin1").strip())
        except ValueError:
            return None
        body, length = offset + 60, size

        # Two archive dialects. GNU keeps long names in a side table and marks the
        # entry with a leading slash; BSD -- which Apple's ar writes, so every iOS
        # static library in this fleet -- stores "#1/<n>" and puts those n bytes of
        # name at the front of the member data. Reading a BSD member as if it were GNU
        # lands n bytes early and the magic never matches, which is why the iOS
        # libraries came back unreadable.
        name = raw_name
        if raw_name.startswith("#1/"):
            try:
                name_length = int(raw_name[3:])
            except ValueError:
                return None
            name = data[body:body + name_length].rstrip(b"\0").decode("latin1")
            body += name_length
            length -= name_length

        # Symbol tables and the long-name table are not objects.
        if not name.startswith(("/", "__.SYMDEF")):
            return data[body:body + length]
        offset = offset + 60 + size + (size % 2)
    return None


def architecture(path):
    data = path.read_bytes()
    if data[:2] == b"MZ":
        return pe_arch(data)
    if data[:4] == b"\x7fELF":
        return elf_arch(data)
    if data[:4] == b"!<ar":
        member = ar_first_member(data)
        if member is None:
            return None
        if member[:4] == b"\0asm":
            return "wasm"
        if member[:4] == b"\x7fELF":
            return elf_arch(member)
        return macho_arch(member)
    if data[:4] == b"\0asm":
        return "wasm"
    return macho_arch(data)


def main():
    manifest_path = Path(sys.argv[1] if len(sys.argv) > 1 else "binding.yml")
    if not manifest_path.exists():
        fail(f"{manifest_path} not found")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    project = manifest.get("package", {}).get("project")
    if not project:
        fail("manifest has no package.project")
    project_dir = Path(project).parent

    # Shared with check-native-coherence.py, so both look in the same places and resolve an
    # Apple framework the same way. Previously this globbed runtimes/*/native/* itself and
    # handed whatever it found to read_bytes(), which raises IsADirectoryError on a
    # .framework -- a crash with no diagnostic, rather than a report.
    natives, path_problems = shipped_natives(manifest, project_dir)
    if not natives and not path_problems:
        print(f"{project_dir} ships no native binaries.")
        return 0

    for rid, reason in path_problems:
        print(f"::warning::{rid}: {reason}")

    wrong, checked, unknown = [], 0, []
    for rid, native in natives:
        expected = EXPECTED.get(rid)
        if expected is None:
            unknown.append(rid)
            continue
        actual = architecture(native)
        checked += 1
        if actual is None:
            # Refusing to guess: an unreadable binary is not a pass.
            wrong.append((native, rid, expected, "unreadable"))
        elif actual != expected:
            wrong.append((native, rid, expected, actual))
        else:
            print(f"  {rid}: {native.name} is {actual}")

    for native, rid, expected, actual in wrong:
        print(f"::error::{native}: {rid} promises {expected}, the binary is {actual}")

    if unknown:
        print(f"::warning::no expected architecture recorded for: "
              f"{', '.join(sorted(set(unknown)))}. Add them to this check rather than "
              f"leaving them unverified.")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Native architectures\n\n")
            fh.write(f"{checked - len(wrong)} of {checked} match the architecture their "
                     f"RID promises.\n")

    if wrong:
        fail(f"{len(wrong)} shipped librar(y/ies) do not match their RID. .NET picks by "
             f"RID, so the wrong one cannot load at all -- and every symbol still looks "
             f"present to a symbol check.")

    if checked == 0:
        fail(f"no recognised RIDs among the natives under {project_dir}; nothing was verified")

    print(f"\nAll {checked} shipped librar(y/ies) match the architecture their RID promises.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
