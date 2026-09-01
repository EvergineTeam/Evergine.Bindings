"""Check that each shipped 64-bit Android library tolerates 16 KB memory pages.

Google Play requires 64-bit native libraries to support 16 KB pages, and from 1 February
2027 it refuses updates that do not. A library that does not is not a build failure and not
a load failure: it links, it runs, every test passes, and the rejection arrives months later
at the person trying to publish an application built on top of this fleet.

The property lives in the ELF program headers. Each PT_LOAD segment carries a p_align, and
the linker writes 0x1000 unless asked for 0x4000 -- by `-Wl,-z,max-page-size=16384`, or by
an NDK from r28 on, where 16 KB became the default. Nothing else in CI can see it: the
architecture check next door reads the machine field and is satisfied, the symbol check
finds every symbol present, and the smoke test loads the library on a runner whose pages
are 4 KB.

Found the hard way in CesiumC, which shipped a 4 KB-aligned arm64 library for as long as it
had shipped Android at all. Nothing in that repository asked for 4 KB: the runner's NDK was
r27c, the flag was absent, and the default did the rest. JoltPhysicsC passed at the same
moment, for a reason equally invisible -- a toolchain option in its workflow that a runner
image bump would have silently stopped honouring.

32-bit is skipped rather than failed. The requirement is 64-bit only and armeabi-v7a is
explicitly excluded, so failing there would be noise that teaches people to ignore this.

Usage: check-native-page-size.py [manifest]
"""

import os
import struct
import sys
from pathlib import Path

import yaml

from native_paths import shipped_natives

# What Google asks for. A LOAD segment aligned to at least this can be mapped on a device
# whose pages are 16 KB; 0x1000 cannot.
REQUIRED_ALIGN = 0x4000

ELF_MAGIC = b"\x7fELF"
PT_LOAD = 1


def fail(message):
    print(f"::error::{message}")
    sys.exit(1)


def load_alignments(data):
    """Every PT_LOAD segment's p_align, or None when the file cannot be read as an ELF.

    Returns (alignments, is_64bit). An empty list with is_64bit set means the file parsed
    but declares no loadable segments, which is not something a shared library does -- the
    caller treats it as a failure rather than as nothing to check.
    """
    if data[:4] != ELF_MAGIC:
        return None, None

    is_64 = data[4] == 2
    little = data[5] == 1
    end = "<" if little else ">"

    try:
        if is_64:
            ph_offset = struct.unpack_from(f"{end}Q", data, 0x20)[0]
            ph_size = struct.unpack_from(f"{end}H", data, 0x36)[0]
            ph_count = struct.unpack_from(f"{end}H", data, 0x38)[0]
        else:
            ph_offset = struct.unpack_from(f"{end}I", data, 0x1C)[0]
            ph_size = struct.unpack_from(f"{end}H", data, 0x2A)[0]
            ph_count = struct.unpack_from(f"{end}H", data, 0x2C)[0]

        alignments = []
        for index in range(ph_count):
            base = ph_offset + index * ph_size
            if struct.unpack_from(f"{end}I", data, base)[0] != PT_LOAD:
                continue
            # p_align is the last field of the program header, and the 32-bit and 64-bit
            # layouts put it in different places: the fields are the same but reordered.
            alignments.append(
                struct.unpack_from(f"{end}Q", data, base + 48)[0] if is_64
                else struct.unpack_from(f"{end}I", data, base + 28)[0]
            )
    except struct.error:
        # A truncated file reads as an ELF for four bytes and then runs out. Report it as
        # unreadable rather than crashing with a traceback and no diagnostic.
        return None, is_64

    return alignments, is_64


def main():
    manifest_path = Path(sys.argv[1] if len(sys.argv) > 1 else "binding.yml")
    if not manifest_path.exists():
        fail(f"{manifest_path} not found")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    project = manifest.get("package", {}).get("project")
    if not project:
        fail("manifest has no package.project")
    project_dir = Path(project).parent

    # Shared with the architecture and symbol checks, so all three look in the same places
    # and resolve an Apple framework the same way.
    natives, path_problems = shipped_natives(manifest, project_dir)

    for rid, reason in path_problems:
        if rid.startswith("android-"):
            print(f"::warning::{rid}: {reason}")

    android = [(rid, native) for rid, native in natives if rid.startswith("android-")]
    if not android:
        # Most of the fleet. Not a failure and not a warning: a package that ships no
        # Android binary has nothing here to get wrong.
        print(f"{project_dir} ships no Android binaries; nothing to check.")
        return 0

    bad, skipped, checked = [], [], 0
    for rid, native in sorted(android):
        alignments, is_64 = load_alignments(native.read_bytes())

        if alignments is None:
            bad.append((native, rid, "not a readable ELF"))
            continue
        if not is_64:
            # The requirement is 64-bit only; armeabi-v7a is excluded by name. Said out
            # loud so a reader can tell "skipped on purpose" from "nobody looked".
            skipped.append(rid)
            continue
        if not alignments:
            bad.append((native, rid, "no PT_LOAD segments"))
            continue

        checked += 1
        worst = min(alignments)
        if worst < REQUIRED_ALIGN:
            bad.append((native, rid, f"aligned to {hex(worst)}"))
        else:
            print(f"  {rid}: {native.name} aligns LOAD segments to {hex(worst)}")

    for native, rid, reason in bad:
        print(f"::error::{native}: {rid} is {reason}, and Google Play requires "
              f"{hex(REQUIRED_ALIGN)} of 64-bit libraries")

    if skipped:
        print(f"Skipped {', '.join(sorted(set(skipped)))}: 32-bit, and the 16 KB "
              f"requirement applies to 64-bit libraries only.")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Android page size\n\n")
            fh.write(f"{checked - len(bad)} of {checked} 64-bit Android librar(y/ies) "
                     f"tolerate 16 KB pages.\n")

    if bad:
        fail(f"{len(bad)} shipped Android librar(y/ies) cannot be mapped on a 16 KB page "
             f"device. Google Play refuses such updates from 1 February 2027, and nothing "
             f"else in CI can see this: it links, loads and passes every test on a 4 KB "
             f"runner. Add -Wl,-z,max-page-size=16384 to the link, or build with NDK r28+.")

    print(f"\nAll {checked} shipped 64-bit Android librar(y/ies) tolerate 16 KB pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
