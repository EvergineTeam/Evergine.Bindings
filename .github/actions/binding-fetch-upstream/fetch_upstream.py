"""Fetch the upstream sources declared in binding.yml and report what changed.

Runs as a deterministic step before the agent starts. Whether a vendored file
differs from upstream is a byte comparison; letting a model discover that costs
turns and produces the same answer.

Writes the new content into the working tree and leaves a short report for the
agent. The agent's job begins where this one ends: interpreting the change and
regenerating, not fetching.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path, PurePosixPath

import yaml

MANIFEST = Path(os.environ.get("MANIFEST", "binding.yml"))
REPORT_PATH = Path(os.environ["REPORT_PATH"])
TOKEN = os.environ.get("GH_TOKEN", "")
# Resolve the tracked release and report, without touching the working tree.
# The caller needs the answer before it can decide whether to spend a
# multi-platform native build on it.
RESOLVE_ONLY = os.environ.get("RESOLVE_ONLY", "").lower() == "true"
# Fetch at the release the manifest records rather than the newest one. Turns this into a
# drift check: what changes is then a difference between the tree and its own declared
# revision, not upstream having moved on.
PIN_RECORDED = os.environ.get("AT_RECORDED_RELEASE", "").lower() == "true"


def fail(message):
    """Abort loudly. A half-fetched tree is worse than no fetch at all."""
    print(f"::error::{message}")
    sys.exit(1)


def normalise_eol(data):
    """Collapse CRLF and lone CR to LF, for comparison only.

    A Windows runner may check the working tree out with CRLF while the download
    arrives with LF. Comparing raw bytes would then report a change on every run
    for a file nobody touched -- and this action's caller commits, regenerates
    and publishes on the strength of that answer. Never compare raw bytes.
    """
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def detect_eol(data):
    """Whichever line ending the vendored file already uses. Preserved on write
    so refreshing a source never reformats the whole file."""
    return b"\r\n" if b"\r\n" in data else b"\n"


def apply_eol(data, eol):
    return normalise_eol(data).replace(b"\n", eol) if eol == b"\r\n" else normalise_eol(data)


def digest(path):
    """Content hash, blind to line endings. See normalise_eol."""
    p = Path(path)
    if not p.exists():
        return None
    if p.is_dir():
        # Directory sources (header trees, submodule mount points) hash as the
        # ordered concatenation of their files, so a rename or deletion counts.
        h = hashlib.sha256()
        for f in sorted(p.rglob("*")):
            if f.is_file():
                h.update(str(f.relative_to(p)).encode())
                h.update(normalise_eol(f.read_bytes()))
        return h.hexdigest()
    return hashlib.sha256(normalise_eol(p.read_bytes())).hexdigest()


def http_get(url, accept=None):
    req = urllib.request.Request(url)
    if TOKEN and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    if accept:
        req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def resolve_release(upstream):
    """Work out which upstream revision this binding should be sitting on.

    Most bindings follow a branch, because a registry or an in-application header
    only ever grows. A binding that ships native binaries cannot: the header and
    the libraries have to come from the same revision, and a branch is a moving
    target. Those declare `release.track` and follow tagged releases instead.

    Returns (resolved, current, moved). All three are None/False when the
    manifest declares no release tracking, which leaves every existing binding
    exactly as it was.
    """
    rel = upstream.get("release")
    if not rel:
        return None, None, False

    track = rel.get("track", "pinned")
    current = rel.get("current")

    # Answer "is the tree in step with the release it says it is on?" rather than "has a
    # newer release appeared?". Those are different questions and only the first belongs
    # in CI: a newer release is news, while a tree that does not match its own recorded
    # release is a defect, and it is the defect that reaches consumers.
    #
    # JoltPhysics.NET had exactly that. Its vendored headers came from `main` while
    # release.current read v5.5.0, whose tag held different content -- so CI regenerated
    # from one thing, the CD fetched another, and the first CD after switching to release
    # tracking committed generated code that did not compile. CI could not have caught it,
    # because CI was reading the stale copy.
    if PIN_RECORDED:
        if not current:
            fail("recorded-release mode needs release.current to be set")
        return current, current, False
    repo = rel.get("repo") or next(
        (s["repo"] for s in upstream.get("sources", []) if s.get("repo")), None
    )

    if track == "pinned":
        if not current:
            fail("release.track is 'pinned' but release.current is not set")
        return current, current, False

    if not repo:
        fail("release tracking needs a repository: set release.repo or a source repo")

    if track == "stable":
        # `releases/latest` is the newest published, non-draft, non-prerelease
        # release -- exactly the semantics wanted, decided by the upstream author
        # rather than by us parsing version strings.
        resolved = json.loads(http_get(f"https://api.github.com/repos/{repo}/releases/latest"))["tag_name"]
    elif track == "latest":
        releases = json.loads(http_get(f"https://api.github.com/repos/{repo}/releases?per_page=1"))
        if not releases:
            fail(f"{repo} publishes no releases; 'latest' cannot be resolved")
        resolved = releases[0]["tag_name"]
    else:
        fail(f"unknown release.track '{track}' (expected stable, latest or pinned)")

    return resolved, current, resolved != current


def probe_version(upstream):
    """Read the upstream version out of a file that is already in the working tree.

    For a vendored upstream there is nothing to ask: no tag, no release API, no package
    registry. The version is a fact about the files somebody committed, so the only
    trustworthy place to read it is those files. That also means nobody has to maintain
    the number by hand -- refreshing the sources updates the manifest in the same commit,
    and the two cannot drift apart.

    Several patterns rather than one, because a version is not always written in one
    place: Vuforia spells it as three separate `#define`s.
    """
    probe = upstream.get("version-probe")
    if not probe:
        return None

    path = Path(probe["file"])
    if not path.exists():
        fail(
            f"version-probe file not found: {path}. It names a vendored file, so its "
            "absence means the manifest and the tree disagree about the layout."
        )

    text = path.read_text(encoding="utf-8", errors="replace")
    parts = []
    for pattern in probe["patterns"]:
        found = re.findall(pattern, text)
        # Exactly one match, and anything else is an error rather than a best guess.
        # Zero is the dangerous one: the file changed shape, and a silent miss would
        # leave this reporting the old version for as long as nobody looked.
        if len(found) != 1:
            fail(
                f"version-probe pattern {pattern!r} matched {len(found)} time(s) in "
                f"{path}, expected exactly 1"
            )
        parts.append(found[0])

    return probe.get("join", ".").join(parts)


def record_release(resolved):
    """Write the resolved tag back into the manifest as the new `current`.

    Edited as text rather than round-tripped through yaml.dump on purpose: these
    manifests carry comments that explain hazards specific to each binding, and
    dumping the parsed document would silently delete every one of them.
    """
    text = MANIFEST.read_text(encoding="utf-8")
    new, count = re.subn(
        r"(?m)^(\s*current:\s*)\S+(.*)$",
        lambda m: f"{m.group(1)}{resolved}{m.group(2)}",
        text,
        count=1,
    )
    if count:
        MANIFEST.write_text(new, encoding="utf-8")
    return bool(count)


def fetch_http_file(source, resolved_ref=None):
    url = source.get("url") or fail("http-file source is missing `url`")
    return {source["path"]: http_get(url)}


def fetch_git_tree(source, resolved_ref=None):
    """Read a file or a directory out of another repository at a pinned ref."""
    repo = source.get("repo") or fail("git-tree source is missing `repo`")
    # An explicit `ref` on the source wins, so a manifest can pin one source
    # while the rest follow the tracked release.
    ref = source.get("ref") or resolved_ref or fail(
        "git-tree source needs `ref`, or an `upstream.release` block to resolve one")
    remote = source.get("remote-path") or fail("git-tree source is missing `remote-path`")
    dest = source["path"]

    meta = json.loads(
        http_get(f"https://api.github.com/repos/{repo}/contents/{remote}?ref={ref}")
    )

    if isinstance(meta, dict):  # single file
        return {dest: http_get(meta["download_url"])}

    files = {}
    stack = list(meta)
    while stack:  # directory: walk it, keeping the layout under `dest`
        entry = stack.pop()
        rel = entry["path"][len(remote):].lstrip("/")
        if entry["type"] == "dir":
            stack.extend(
                json.loads(
                    http_get(
                        f"https://api.github.com/repos/{repo}/contents/{entry['path']}?ref={ref}"
                    )
                )
            )
        elif entry["type"] == "file":
            files[str(Path(dest) / rel)] = http_get(entry["download_url"])
    return files


def fetch_release_assets(assets, repo, tag):
    """Unpack binaries published as assets of the release the sources came from.

    A binding that ships native libraries needs them to match the headers it was
    generated from. Where the libraries are built in the same repository, the CD builds
    them in the same run and hands them over as artifacts -- that is what
    `natives-artifact-pattern` is for. This is the other shape: the libraries are built
    somewhere else, and the only durable link between a library and the revision it was
    compiled from is the release it is attached to.

    Artifacts cannot serve here. They expire -- every one of the 42 that
    EvergineTeam/JoltPhysicsC had produced was already gone -- and they carry no version.
    Calling the other repository's build as a reusable workflow cannot serve either:
    `uses:` takes no expression, so the tag would have to be edited by hand on every bump,
    which is the manual step this exists to remove.

    Returns {path: bytes}, the same shape the other adapters return, so the caller decides
    what has actually changed rather than this function guessing.
    """
    import fnmatch
    import io
    import zipfile

    meta = json.loads(
        http_get(f"https://api.github.com/repos/{repo}/releases/tags/{tag}")
    )
    published = {a["name"]: a for a in meta.get("assets", [])}

    files = {}
    for spec in assets:
        pattern = spec.get("name") or fail("assets entry is missing `name`")
        into = Path(spec.get("into", "."))

        matched = [published[n] for n in sorted(published) if fnmatch.fnmatch(n, pattern)]
        if not matched:
            fail(
                f"no asset on {repo} {tag} matches '{pattern}'. Published: "
                + (", ".join(sorted(published)) or "none")
            )

        for asset in matched:
            # The API url with this Accept returns the bytes; browser_download_url works
            # for a public repository and not for a private one.
            blob = http_get(asset["url"], accept="application/octet-stream")

            if spec.get("unpack") == "zip":
                with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                    for entry in zf.namelist():
                        if entry.endswith("/"):
                            continue
                        # An archive is upstream input, so its member names are untrusted:
                        # an entry named ../../.github/workflows/ci.yml would otherwise be
                        # written wherever it asked.
                        #
                        # Parsed as POSIX because that is what a zip member name is, and
                        # because the host's flavour gets this wrong in a way that matters.
                        # On Windows, Path("/etc/passwd").is_absolute() is False -- there is
                        # no drive letter -- and joining a rooted path discards the left
                        # side, so `into / rel` escaped the destination entirely. The guard
                        # was effective on Linux and not on the runner this feature is for.
                        rel = PurePosixPath(entry)
                        if rel.is_absolute() or ".." in rel.parts:
                            fail(f"asset {asset['name']} contains unsafe path '{entry}'")

                        target = into.joinpath(*rel.parts)
                        # Belt and braces: whatever the parsing decided, the file has to
                        # land inside `into`.
                        if not target.resolve().is_relative_to(into.resolve()):
                            fail(f"asset {asset['name']} escapes {into} with '{entry}'")

                        files[str(target)] = zf.read(entry)
            else:
                files[str(into / asset["name"])] = blob

    return files


def submodule_state(source):
    """Compare the recorded submodule SHA with the upstream head.

    Reads only. Whether the pointer then moves is decided by `upstream.bump`, which
    defaults to reporting, because for some bindings a bump means rebuilding native
    binaries for every platform they ship.
    """
    path = source["path"]
    repo = source.get("repo") or fail("git-submodule source is missing `repo`")
    recorded = subprocess.run(
        ["git", "ls-tree", "HEAD", path],
        capture_output=True, text=True, check=False,
    ).stdout.split()
    local_sha = recorded[2] if len(recorded) >= 3 else None

    info = json.loads(http_get(f"https://api.github.com/repos/{repo}"))
    head = json.loads(
        http_get(f"https://api.github.com/repos/{repo}/commits/{info['default_branch']}")
    )["sha"]
    return local_sha, head


def git(args, cwd=None):
    """Run git, failing loudly. A half-moved set of submodules is worse than none."""
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def bump_submodule(path, sha):
    """Move one submodule to a revision.

    The working copy may be shallow, so ask for the single commit rather than the
    whole history; a checkout is not enough on its own when the object is absent.
    """
    if not Path(path, ".git").exists() and not Path(path).is_dir():
        fail(f"{path} is not checked out -- the caller must clone submodules")
    try:
        git(["fetch", "--depth", "1", "origin", sha], cwd=path)
    except SystemExit:
        git(["fetch", "origin"], cwd=path)
    git(["checkout", "--detach", sha], cwd=path)


def apply_exports(source):
    """Copy declared files out of the submodule into the repository.

    These are the generated definitions the C# generators read. They live inside the
    submodule already, so copying them from there -- rather than fetching them
    separately -- makes it impossible for the definitions and the binaries built from
    the same revision to disagree. Before this existed the copy was a documented
    manual step, and nothing failed when it was skipped.
    """
    copied = []
    for export in source.get("exports", []):
        src = Path(source["path"]) / export["from"]
        dest = Path(export["to"])
        if not src.exists():
            fail(f"export source {src} not found after bumping {source['path']}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Keep whatever line ending the destination already uses, for the same reason
        # every other write in this file does: a Windows runner would otherwise
        # rewrite the whole file and report a change nobody made.
        eol = detect_eol(dest.read_bytes()) if dest.exists() else None
        content = src.read_bytes()
        dest.write_bytes(apply_eol(content, eol) if eol else content)
        copied.append(str(dest))
    return copied


def main():
    if not MANIFEST.exists():
        fail(f"{MANIFEST} not found. The updater cannot run without a manifest.")

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    upstream = manifest["upstream"]
    kind = upstream["kind"]
    lines = [f"# Upstream check\n", f"Adapter: `{kind}`  \n"]
    changed = False

    submodule_heads = ""
    resolved_ref, previous_ref, ref_moved = resolve_release(upstream)

    # A vendored upstream has no tag to resolve, so the version comes from the sources
    # themselves and overrides whatever the release block said. This also makes
    # resolve-only mode useful here: without it, a manifest with `track: pinned` would
    # report its own recorded value back and never notice that the tree had moved past it.
    if kind == "vendored":
        probed = probe_version(upstream)
        if probed:
            previous_ref = (upstream.get("release") or {}).get("current")
            resolved_ref = probed
            ref_moved = probed != previous_ref

    if resolved_ref:
        track = upstream["release"].get("track", "pinned")
        lines.append(
            f"Release tracking: `{track}`  \n"
            f"- vendored: `{previous_ref or 'none recorded'}`  \n"
            f"- resolved: `{resolved_ref}`"
            f"{'  **(new release available)**' if ref_moved else ' (up to date)'}  \n"
        )

    if RESOLVE_ONLY:
        # Submodule manifests have no release block, so resolve_release said nothing
        # moved and callers skipped the work -- while the fetch that runs later, in
        # normal mode, went ahead and bumped. ImGui.Net landed four bumped pointers,
        # refreshed definitions and regenerated bindings on main with the native
        # libraries left at the old revision: 24 declared symbols exported by nothing.
        # Exactly the mismatch this adapter exists to prevent.
        if kind == "git-submodule":
            heads = {}
            for source in upstream["sources"]:
                local_sha, head = submodule_state(source)
                same = local_sha == head
                ref_moved = ref_moved or not same
                heads[source["path"]] = head
                lines.append(
                    f"- `{source['path']}` ({source['repo']}): "
                    f"{'up to date' if same else '**behind upstream**'}  \n"
                    f"  recorded `{(local_sha or 'unknown')[:12]}` / "
                    f"upstream `{head[:12]}`\n"
                )
            resolved_ref = resolved_ref or ("moved" if ref_moved else "")
            # Handed to whoever builds the native libraries, so they compile the same
            # revision this run is going to commit. Without it that job checks out the
            # recorded pointers -- the old ones, since the bump happens later -- and
            # produces libraries for the revision being replaced. The result passes
            # every gate and is exactly the mismatch the gates exist to prevent.
            submodule_heads = json.dumps(heads, sort_keys=True)

        lines.append("\n_Resolve-only: nothing fetched, nothing written._\n")
        REPORT_PATH.write_text("".join(lines), encoding="utf-8")
        print("".join(lines))
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"changed={'true' if ref_moved else 'false'}\n")
            fh.write(f"report={REPORT_PATH}\n")
            fh.write(f"resolved_ref={resolved_ref or ''}\n")
            fh.write(f"previous_ref={previous_ref or ''}\n")
            fh.write(f"ref_moved={'true' if ref_moved else 'false'}\n")
            fh.write(f"submodule_heads={submodule_heads}\n")
        return

    if kind == "vendored":
        # Fetches nothing and writes nothing, and that is the whole point: some upstreams
        # cannot be downloaded by a machine. Vuforia's SDK is behind a sign-in and a licence
        # acceptance, so the headers arrive by hand and live in the repository. This adapter
        # exists so such a repository can still use the manifest-driven CD -- which is the
        # only one that commits regenerated output -- instead of being locked out of it.
        #
        # `changed` stays false deliberately. Nothing was brought in by this step; the
        # sources were already committed by whoever dropped them in. Reporting true would
        # trip the tracked CD's refusal to commit a source bump with no matching native
        # rebuild, and that refusal is right to exist -- it just does not apply when the
        # human committed the sources and the binaries together in one go.
        for source in upstream["sources"]:
            path = Path(source["path"])
            if not path.exists():
                fail(
                    f"vendored source not found: {path}. Nothing fetches this upstream, "
                    "so the sources must be in the tree."
                )
            lines.append(
                f"- `{source['path']}` ({source['format']}): vendored, "
                f"{sum(1 for _ in path.rglob('*') if _.is_file()) if path.is_dir() else 1} "
                "file(s) present\n"
            )

        if ref_moved:
            lines.append(
                f"\n**The vendored sources are at `{resolved_ref}` and the manifest recorded "
                f"`{previous_ref or 'nothing'}`.** Somebody refreshed them; regenerate so the "
                "generated code catches up.\n"
            )
        else:
            lines.append(
                f"\nVendored sources at `{resolved_ref or 'an unrecorded version'}`, matching "
                "the manifest. There is nothing to fetch and nothing to bring up to date.\n"
            )
    elif kind == "git-submodule":
        bump = upstream.get("bump", "report-only")
        if bump not in ("report-only", "together"):
            fail(f"unknown upstream.bump '{bump}' (expected report-only or together)")

        # Every head is resolved before anything moves. Under `together` the set has to
        # land as one revision: these submodules compile into a single binary and share
        # C++ headers, so a half-applied bump is a combination upstream never built.
        states = []
        for source in upstream["sources"]:
            local_sha, head = submodule_state(source)
            same = local_sha == head
            changed = changed or not same
            states.append((source, local_sha, head, same))
            state = "up to date" if same else "**behind upstream**"
            lines.append(
                f"- `{source['path']}` ({source['repo']}): {state}  \n"
                f"  recorded `{(local_sha or 'unknown')[:12]}` / upstream `{head[:12]}`\n"
            )

        if bump == "report-only":
            lines.append(
                "\n> `bump: report-only`. Report it and stop -- moving this pointer means "
                "rebuilding native binaries, which is not this step's job.\n"
            )
        elif changed:
            for source, _, head, _ in states:
                bump_submodule(source["path"], head)
            exported = []
            for source, _, _, _ in states:
                exported += apply_exports(source)
            lines.append(
                f"\n**Bumped {len(states)} submodule(s) as a set.**\n"
            )
            if exported:
                lines.append(
                    f"Copied {len(exported)} declared file(s) out of the submodules, so the "
                    f"definitions and the binaries come from the same revision:\n"
                    + "".join(f"- `{p}`\n" for p in exported)
                )
        else:
            lines.append("\nAll submodules already at upstream head.\n")
    else:
        fetcher = {"http-file": fetch_http_file, "git-tree": fetch_git_tree}.get(kind)
        if fetcher is None:
            fail(f"unknown upstream.kind '{kind}'")

        for source in upstream["sources"]:
            before = digest(source["path"])
            payload = fetcher(source, resolved_ref)
            for dest, content in payload.items():
                target = Path(dest)
                target.parent.mkdir(parents=True, exist_ok=True)
                # Keep whatever line ending the vendored file already uses, so a
                # refresh changes the declarations and nothing else. A new file
                # lands as downloaded.
                eol = detect_eol(target.read_bytes()) if target.exists() else None
                target.write_bytes(apply_eol(content, eol) if eol else content)
            after = digest(source["path"])
            same = before == after
            changed = changed or not same
            size = sum(len(c) for c in payload.values())
            lines.append(
                f"- `{source['path']}` ({source['format']}): "
                f"{'unchanged' if same else '**updated**'}, {size:,} bytes\n"
            )

    # Assets are orthogonal to `kind`: a binding can take its headers out of a repository
    # tree and its libraries from a release of that same repository, which is exactly the
    # case this was added for. So this runs after whichever adapter ran, not instead of one.
    asset_roots = set()
    for spec in upstream.get("assets", []):
        repo = spec.get("repo") or (upstream.get("release") or {}).get("repo") or fail(
            "assets need a repository: set assets[].repo or release.repo")
        tag = spec.get("tag") or resolved_ref or fail(
            "assets need a tag: set assets[].tag, or a release block to resolve one")

        payload = fetch_release_assets([spec], repo, tag)

        # Compared byte for byte against what is already committed, so republishing the
        # same release -- or rebuilding it and getting identical output -- is correctly
        # read as no change. Deciding this by "did we write a file" would make every run
        # look like a bump and publish a package on each one.
        moved = 0
        for dest, content in sorted(payload.items()):
            target = Path(dest)
            if not target.exists() or target.read_bytes() != content:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                moved += 1
            # `root` is what the caller subtracts from its changed-file list. Reported as
            # the first path segment under `into`, so one entry covers every library
            # beneath it instead of ten.
            rel = target.relative_to(Path(spec.get("into", ".")))
            # as_posix, so the value does not depend on which runner unpacked it. The
            # caller normalises separators anyway; not relying on that is cheaper than
            # finding out it stopped.
            asset_roots.add((Path(spec.get("into", ".")) / rel.parts[0]).as_posix())

        changed = changed or moved > 0
        lines.append(
            f"- `{spec['name']}` from {repo} `{tag}`: {len(payload)} file(s), "
            f"{'**' + str(moved) + ' updated**' if moved else 'all identical'}\n"
        )

    # Worded per kind. `changed` means "this step brought something in", which for a
    # vendored upstream is false even when the sources have just been replaced -- so
    # printing "nothing changed" straight after "somebody refreshed them, regenerate"
    # reads as a contradiction to whoever, or whatever, is acting on this report.
    if kind == "vendored":
        result = "vendored sources refreshed" if ref_moved else "vendored sources unchanged"
    else:
        result = "sources changed" if changed else "nothing changed"
    lines.append(f"\n**Result: {result}.**\n")
    # Not said for a vendored upstream, where `changed` is false by construction. "Call
    # noop and stop" would be the wrong instruction twice over: when the sources have just
    # been refreshed there is plenty to regenerate, and when they have not, an agent woken
    # by `agent:needs-regen` was called in to repair a failure rather than to chase a bump.
    if not changed and kind != "vendored":
        lines.append(
            "\nNo upstream movement. Call `noop` and stop -- there is nothing to regenerate.\n"
        )
    elif kind == "vendored" and not ref_moved:
        lines.append(
            "\nNothing to fetch. If you were woken to chase an upstream bump, `noop` and "
            "stop; if you were woken to repair a failure, the sources you need are already "
            "here.\n"
        )

    # Record the release only once the fetch has succeeded, so a manifest never
    # claims a version whose sources failed to land. A vendored upstream satisfies that
    # by definition -- the sources were committed before this step ran -- so the version
    # read out of them is recorded even though nothing was fetched.
    if ref_moved and resolved_ref and (changed or kind == "vendored"):
        record_release(resolved_ref)
        lines.append(f"\nManifest updated: `release.current` is now `{resolved_ref}`.\n")

    REPORT_PATH.write_text("".join(lines), encoding="utf-8")
    print("".join(lines))

    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        fh.write(f"changed={'true' if changed else 'false'}\n")
        fh.write(f"report={REPORT_PATH}\n")
        fh.write(f"resolved_ref={resolved_ref or ''}\n")
        fh.write(f"previous_ref={previous_ref or ''}\n")
        fh.write(f"ref_moved={'true' if ref_moved else 'false'}\n")
        # The caller subtracts these from the set of changed files to work out
        # whether the *generated* code moved, or only the sources it was
        # generated from. action.yml has always advertised this output and
        # nothing ever wrote it, so the caller received an empty list and
        # counted every fetched source as a generated change -- publishing a
        # package whenever upstream moved, even when the API was identical.
        fh.write("paths<<__EOF__\n")
        for source in upstream.get("sources", []):
            if source.get("path"):
                fh.write(f"{source['path']}\n")
            # Export destinations are fetched sources too -- copied out of a submodule
            # rather than downloaded, but not generator output. Left out, the caller
            # would read them as a changed API and publish on a definitions refresh
            # that regenerated to identical code.
            for export in source.get("exports", []):
                fh.write(f"{export['to']}\n")
        # Same reasoning for release assets: they are fetched input, not generator output.
        # Left out, a rebuilt native library would read as a changed API and publish a
        # package whose managed surface is identical.
        for root in sorted(asset_roots):
            fh.write(f"{root}\n")
        fh.write("__EOF__\n")
        # The tracked CD refuses to commit a source bump for a package that ships native
        # binaries unless someone handed the binaries over. It knew one way of doing that
        # -- artifacts from the same run -- so without this it would block the case where
        # they arrive from a release instead.
        fh.write(f"natives_from_release={'true' if asset_roots else 'false'}\n")


if __name__ == "__main__":
    main()
