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
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

MANIFEST = Path(os.environ.get("MANIFEST", "binding.yml"))
REPORT_PATH = Path(os.environ["REPORT_PATH"])
TOKEN = os.environ.get("GH_TOKEN", "")


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


def fetch_http_file(source):
    url = source.get("url") or fail("http-file source is missing `url`")
    return {source["path"]: http_get(url)}


def fetch_git_tree(source):
    """Read a file or a directory out of another repository at a pinned ref."""
    repo = source.get("repo") or fail("git-tree source is missing `repo`")
    ref = source.get("ref") or fail("git-tree source is missing `ref`")
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


def submodule_state(source):
    """Compare the recorded submodule SHA with the upstream head.

    Deliberately does not check anything out. For KTX.NET and ImGui.Net a pointer
    bump means rebuilding native binaries or moving four interdependent modules
    together, so this adapter reports and stops -- the manifests say as much.
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


def main():
    if not MANIFEST.exists():
        fail(f"{MANIFEST} not found. The updater cannot run without a manifest.")

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    upstream = manifest["upstream"]
    kind = upstream["kind"]
    lines = [f"# Upstream check\n", f"Adapter: `{kind}`  \n"]
    changed = False

    if kind == "git-submodule":
        for source in upstream["sources"]:
            local_sha, head = submodule_state(source)
            same = local_sha == head
            changed = changed or not same
            state = "up to date" if same else "**behind upstream**"
            lines.append(
                f"- `{source['path']}` ({source['repo']}): {state}  \n"
                f"  recorded `{(local_sha or 'unknown')[:12]}` / upstream `{head[:12]}`\n"
            )
        lines.append(
            "\n> A submodule bump is never automatic here. Report it and stop unless the "
            "manifest explicitly says otherwise.\n"
        )
    else:
        fetcher = {"http-file": fetch_http_file, "git-tree": fetch_git_tree}.get(kind)
        if fetcher is None:
            fail(f"unknown upstream.kind '{kind}'")

        for source in upstream["sources"]:
            before = digest(source["path"])
            payload = fetcher(source)
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

    lines.append(
        f"\n**Result: {'sources changed' if changed else 'nothing changed'}.**\n"
    )
    if not changed:
        lines.append(
            "\nNo upstream movement. Call `noop` and stop -- there is nothing to regenerate.\n"
        )

    REPORT_PATH.write_text("".join(lines), encoding="utf-8")
    print("".join(lines))

    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        fh.write(f"changed={'true' if changed else 'false'}\n")
        fh.write(f"report={REPORT_PATH}\n")


if __name__ == "__main__":
    main()
