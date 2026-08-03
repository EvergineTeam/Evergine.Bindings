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
