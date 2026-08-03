"""Check that every file copied out of a submodule still matches its source.

A binding whose generator reads definitions produced inside a submodule keeps a copy
of them in the repository. Those two must agree: the copy is what the generator turns
into C#, and the submodule is what gets compiled into the native library. If they
drift, the managed layer describes one revision and the binary is another -- and
nothing else notices, because both halves build cleanly.

For ImGui.Net this was a step written down in pipelines.md ("Copiar generator/output
... hacia imguiGen/Jsons") that no workflow performed. This check is what makes
forgetting it visible.

Exact and free: a byte comparison of files already on disk, no compilation, no
network. Reads `exports` from the manifest, so it needs no configuration of its own.

Usage: check-exports-fresh.py [manifest]
"""

import hashlib
import os
import sys
from pathlib import Path

import yaml


def fail(message):
    print(f"::error::{message}")
    sys.exit(1)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalised_digest(path):
    """Hash blind to line endings.

    The copy is written preserving whatever convention the destination already used,
    so on a Windows checkout it can legitimately differ from the submodule byte for
    byte while being the same content. Comparing raw bytes here would report drift on
    every run -- the same mistake this project has made three times.
    """
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def main():
    manifest_path = Path(sys.argv[1] if len(sys.argv) > 1 else "binding.yml")
    if not manifest_path.exists():
        fail(f"{manifest_path} not found")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    sources = manifest.get("upstream", {}).get("sources", [])
    pairs = [
        (Path(source["path"]) / export["from"], Path(export["to"]))
        for source in sources
        for export in source.get("exports", [])
    ]

    if not pairs:
        print("This manifest declares no exports. Nothing to check.")
        return 0

    missing_submodule = [src for src, _ in pairs if not src.exists()]
    if missing_submodule:
        fail(f"{missing_submodule[0]} is absent -- submodules are probably not checked "
             f"out, so this check cannot tell fresh from stale and must not pass")

    stale, checked = [], 0
    for src, dest in pairs:
        if not dest.exists():
            stale.append((dest, "never copied"))
            continue
        checked += 1
        if normalised_digest(src) != normalised_digest(dest):
            stale.append((dest, f"differs from {src}"))

    for dest, why in stale:
        print(f"::error::{dest}: {why}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Exported definitions\n\n")
            fh.write(f"{len(pairs) - len(stale)} of {len(pairs)} match the submodule "
                     f"they came from.\n")

    if stale:
        fail(f"{len(stale)} of {len(pairs)} exported file(s) do not match their "
             f"submodule. The generator would read one revision while the native "
             f"library is built from another.")

    print(f"All {checked} exported file(s) match the submodule they came from.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
