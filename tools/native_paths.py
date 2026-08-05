"""Work out which native libraries a package publishes, and where each one really is.

Shared by check-native-coherence.py and check-native-arch.py. It exists as one module
rather than two copies because the awkward part -- an Apple framework is a directory and
the thing to read is inside it -- is exactly the kind of logic that rots when duplicated:
one copy gets a fix and the other quietly keeps failing.

Two sources, and both are needed:

  runtimes/<rid>/native/<file>   the convention almost every package in this fleet follows,
                                where the RID is a path segment
  package.natives[]             declared, for the ones that cannot follow it

Vuforia.NET is why the second exists. Its iOS payload is an Apple framework staged for
consumers at buildTransitive/ios/VuforiaEngine.framework, outside runtimes/ entirely, so
there is no RID in the path to read and no file at the end of the glob -- the framework is
a directory. Assuming the convention meant that platform went unchecked, and a package
half-checked reports as a package checked.
"""

from pathlib import Path

# What the export dumper and the architecture reader can make sense of. An extensionless
# file is included on purpose: the binary inside an Apple framework has no suffix, and both
# readers dispatch on magic bytes rather than on the name.
LIBRARY_SUFFIXES = (".dll", ".so", ".dylib", ".a")


def is_library(path):
    """Whether this is a file the readers can be handed."""
    return path.is_file() and (path.suffix.lower() in LIBRARY_SUFFIXES or not path.suffix)


def framework_binary(bundle):
    """The executable inside an Apple framework bundle, or None.

    Two layouts. iOS and tvOS use a flat bundle with the binary at the top level; macOS
    uses a versioned one and reaches it through Versions/Current. Both are tried, and
    Versions/* last so a bundle with no Current symlink -- which is what a zip round-trip
    tends to produce -- still resolves.
    """
    name = bundle.name[: -len(".framework")]
    candidates = [
        bundle / name,
        bundle / "Versions" / "Current" / name,
        *sorted(bundle.glob(f"Versions/*/{name}")),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def resolve(entry):
    """Turn a declared or discovered path into the file to read.

    Returns (path, None) when there is something readable, or (None, reason) when there is
    not. A reason rather than a bare None because "this platform could not be checked" has
    to be reportable: the whole point of these checks is that a platform nobody looked at
    is named out loud instead of quietly dropped.
    """
    if entry.is_dir():
        if entry.name.endswith(".framework"):
            binary = framework_binary(entry)
            if binary is None:
                return None, f"{entry} is a framework with no binary inside it"
            return binary, None
        return None, f"{entry} is a directory and not an Apple framework"

    if not entry.exists():
        return None, f"{entry} does not exist"

    if not is_library(entry):
        return None, f"{entry} is not a library this check can read"

    return entry, None


def shipped_natives(manifest, project_dir):
    """Every native library the package publishes.

    Returns (entries, problems): entries is a list of (rid, path) ready to read, problems is
    a list of (rid, reason) for anything declared or discovered that could not be resolved.
    Problems are returned rather than raised so the caller decides -- a stray file under
    runtimes/ is a warning, while a declared path that does not resolve is a defect.
    """
    entries, problems = [], []

    runtimes = project_dir / "runtimes"
    if runtimes.is_dir():
        for found in sorted(runtimes.glob("*/native/*")):
            rid = found.parent.parent.name
            path, reason = resolve(found)
            if path is None:
                problems.append((rid, reason))
            else:
                entries.append((rid, path))

    # Declared entries are held to a higher standard than discovered ones: somebody wrote
    # this path down, so if it does not resolve the manifest is wrong and saying so is more
    # useful than skipping it.
    for declared in (manifest.get("package") or {}).get("natives") or []:
        rid = declared.get("rid")
        raw = declared.get("path")
        if not rid or not raw:
            problems.append((rid or "?", f"package.natives entry needs both path and rid: {declared}"))
            continue
        path, reason = resolve(Path(raw))
        if path is None:
            problems.append((rid, f"declared {reason}"))
        else:
            entries.append((rid, path))

    return entries, problems
