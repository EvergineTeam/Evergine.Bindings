"""Print the exported symbols of a shared library, one per line, sorted.

For bindings that ship native binaries, the exported symbol set *is* the contract
the managed P/Invokes bind against. Recording it turns a native rebuild from an
act of faith into something reviewable: the libraries are never byte-identical
across builds -- different compiler, different date -- so bytes prove nothing,
while a symbol that used to be there and now is not means the package will throw
in the consumer's application.

Reads the binary format directly rather than shelling out to nm or dumpbin.
Those are not present on every runner, need a different invocation per platform,
and print prose that has to be scraped -- scraping dumpbin picked up the DLL's
own name and fragments of decorated C++ names as if they were exports, which is
exactly the kind of noise that makes a comparison useless when it matters.

Usage: dump-exports.py <library> [prefix]
"""

import struct
import sys


def pe_exports(path):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    entry = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
    return {s.name.decode() for s in entry.symbols if s.name} if entry else set()


def elf_exports(path):
    from elftools.elf.elffile import ELFFile
    with open(path, "rb") as fh:
        section = ELFFile(fh).get_section_by_name(".dynsym")
        if section is None:
            return set()
        # Defined and globally visible: what a consumer can actually bind to.
        return {
            sym.name for sym in section.iter_symbols()
            if sym.name
            and sym["st_shndx"] != "SHN_UNDEF"
            and sym["st_info"]["bind"] in ("STB_GLOBAL", "STB_WEAK")
        }


def macho_exports(path):
    from macholib.MachO import MachO
    from macholib.SymbolTable import SymbolTable
    from macholib.mach_o import N_EXT, N_TYPE, N_UNDF
    names = set()
    macho = MachO(path)
    for header in macho.headers:
        for nlist, name in SymbolTable(macho, header).nlists:
            if not name:
                continue
            if isinstance(name, bytes):
                name = name.decode()
            if (nlist.n_type & N_EXT) and (nlist.n_type & N_TYPE) != N_UNDF:
                # Mach-O prefixes C symbols with an underscore.
                names.add(name.lstrip("_"))
    return names


def ar_exports(path):
    """Defined symbols of a static archive, read from its symbol index.

    Three platforms in this fleet ship `.a` rather than a shared library -- iOS, the iOS
    simulator and WebAssembly -- and until now none of them were checked at all: the
    coherence check skipped any extension it did not recognise, silently, and this dumper
    would have crashed on them if it had been asked. So the platforms that cannot be
    smoke-tested were also the ones nothing verified statically.

    Read from the archive's own symbol index rather than by parsing each member. That is
    what makes this work for WebAssembly: the members are wasm objects, and decoding those
    would mean implementing the linking section, while the index is the same handful of
    bytes whatever the members contain.

    Both dialects appear here, so both are handled: Apple's `libtool` writes BSD
    (`__.SYMDEF`, little-endian), and Emscripten's `llvm-ar` writes GNU (`/`, big-endian).
    """
    with open(path, "rb") as fh:
        data = fh.read()

    if data[:8] != b"!<arch>\n":
        raise ValueError(f"{path} is not an ar archive")

    # The 60-byte header sits at offset 8, after the magic, so every field is offset by
    # that: name 8..24, mtime, uid, gid, mode 48..56, size 56..66, then "`\n" and the body
    # at 68. Reading size at 48 gets the mode instead, which parses as a plausible number
    # and then indexes the wrong bytes.
    raw_name = data[8:24].decode("ascii", "replace")
    size = int(data[56:66].decode("ascii", "replace").strip())
    body = 68
    name = raw_name.strip()

    # BSD stores a long name inline: "#1/<n>" means the next n bytes of the body are the
    # name. That is how __.SYMDEF SORTED arrives, and reading the 16-byte field alone
    # makes an Apple archive look like it has no index.
    if name.startswith("#1/"):
        n = int(name[3:])
        name = data[body:body + n].split(b"\0")[0].decode("ascii", "replace")
        body += n
        size -= n

    table = data[body:body + size]
    names = set()

    if name.startswith("__.SYMDEF"):
        (ranlib_bytes,) = struct.unpack_from("<I", table, 0)
        count = ranlib_bytes // 8
        strings_at = 4 + ranlib_bytes + 4
        for i in range(count):
            (str_off, _member) = struct.unpack_from("<II", table, 4 + i * 8)
            end = table.index(b"\0", strings_at + str_off)
            names.add(table[strings_at + str_off:end].decode("ascii", "replace"))
    elif name == "/" or name == "":
        (count,) = struct.unpack_from(">I", table, 0)
        cursor = 4 + count * 4
        for _ in range(count):
            end = table.index(b"\0", cursor)
            names.add(table[cursor:end].decode("ascii", "replace"))
            cursor = end + 1
    else:
        raise ValueError(
            f"{path} has no symbol index -- first member is '{name}'. An archive without "
            f"one cannot be checked; rebuild it with ranlib or llvm-ar.")

    # Mach-O prefixes every C symbol with an underscore, same as the dylib reader strips.
    return {n.lstrip("_") for n in names}


def main():
    if len(sys.argv) < 2:
        print("usage: dump-exports.py <library> [prefix]", file=sys.stderr)
        return 2

    path = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else ""

    with open(path, "rb") as fh:
        magic = fh.read(4)

    if magic[:2] == b"MZ":
        names = pe_exports(path)
    elif magic == b"\x7fELF":
        names = elf_exports(path)
    elif magic == b"!<ar":
        names = ar_exports(path)
    else:
        names = macho_exports(path)

    selected = sorted(n for n in names if n.startswith(prefix))
    if not selected:
        print(f"::error::{path} exports nothing matching '{prefix}' -- "
              f"the library is not what we think it is", file=sys.stderr)
        return 1

    print("\n".join(selected))
    return 0


if __name__ == "__main__":
    sys.exit(main())
