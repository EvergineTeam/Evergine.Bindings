"""Collect fleet metrics into agents-data.json for the dashboard.

Reads only. Nothing here writes to a binding repository: every figure comes from
the GitHub API, from `gh aw audit`, or from nuget.org. A binding does not have to
publish anything for it to appear on the dashboard.

The output keeps FrameStudio's RunRecord shape so the two panels stay legible to
the same reader, plus two fields this domain needs: `repo`, because we have a
fleet rather than one repository, and `credits`, because Copilot bills in AI
Credits since 2026-06-01.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ORG = os.environ.get("FLEET_ORG", "EvergineTeam")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = Path(os.environ.get("OUT", "dashboard/src/data/agents-data.json"))
# How far back to look. Ninety days covers three monthly cycles, which is the
# shortest window in which "did the monthly job run" is answerable.
WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "90"))

AGENT_WORKFLOWS = {"CI Doctor", "Binding Updater", "Toolbox Updater"}
PIPELINE_WORKFLOWS = {"CI", "CD", "Sync standards"}

FLEET = [
    "Vulkan.NET", "OpenXR.NET", "OpenGL.NET", "WebGPU.NET", "KTX.NET",
    "ImGui.Net", "xatlas.NET", "Meshoptimizer.NET", "RenderDoc.NET",
    "JoltPhysics.NET", "Cesium.NET",
]


def api(path, paginate=False):
    """GET the GitHub API. Returns None rather than raising: one repository
    without a given resource must not take the whole dashboard down."""
    results = []
    url = f"https://api.github.com/{path.lstrip('/')}"
    while url:
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github+json")
        if TOKEN:
            req.add_header("Authorization", f"Bearer {TOKEN}")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read())
                link = resp.headers.get("Link", "")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return [] if paginate else None
            print(f"::warning::{path} -> HTTP {exc.code}")
            return [] if paginate else None
        if not paginate:
            return payload
        results.extend(payload if isinstance(payload, list) else payload.get("workflow_runs", []))
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part[part.find("<") + 1:part.find(">")]
                break
    return results


def toolbox_releases():
    """Release tags newest-first, with the commit each points at.

    The moving `v1` tag is excluded: it is an alias, not a release, and counting
    it would make every repository look one version behind forever.
    """
    tags = api(f"repos/{ORG}/Evergine.Bindings/tags?per_page=100", paginate=True) or []
    releases = [
        (t["name"], t["commit"]["sha"])
        for t in tags
        if t["name"].count(".") == 2 and t["name"].startswith("v")
    ]

    def key(name):
        return tuple(int(p) for p in name[1:].split("."))

    return sorted(releases, key=lambda r: key(r[0]), reverse=True)


def consumer_state(repo):
    """Whether a repository calls the toolbox's reusable workflows, and at which ref.

    Used for the repositories that have no agents installed. They still run the
    toolbox's CI, CD, upstream resolution and gates -- they just have nothing
    compiled locally, so there is no pin to drift and nothing to be behind.
    """
    listing = api(f"repos/{ORG}/{repo}/contents/.github/workflows") or []
    refs = set()
    for entry in listing:
        if not entry["name"].endswith((".yml", ".yaml")):
            continue
        content = api(f"repos/{ORG}/{repo}/contents/.github/workflows/{entry['name']}")
        if not content or "content" not in content:
            continue
        import base64
        import re as _re
        text = base64.b64decode(content["content"]).decode("utf-8", "replace")
        refs.update(_re.findall(
            r"EvergineTeam/Evergine\.Bindings/\.github/workflows/[^@\s]+@(\S+)", text))

    if not refs:
        return None
    return {
        "sha": None,
        # A moving tag, resolved per run. Reported as the ref rather than a
        # release number, because that is what the repository actually declares.
        "version": sorted(refs)[0] if len(refs) == 1 else "mixed",
        "behind": 0,
        "latest": None,
        "agents_differ": None,
        "consumer_only": True,
        "workflow_refs": sorted(refs),
    }


def toolbox_state(repo, releases, current_agents):
    """Which toolbox release a repository's installed agents came from.

    Two different questions, and they do not always agree:

      `behind`        how many releases have shipped since the pin. This is what
                      the dashboard colours, because it is what a reader means by
                      "is it up to date".
      `agents_differ` whether the installed workflow text actually differs from
                      the current one. A release that only touched a reusable CI
                      workflow leaves the agents byte-identical, and saying a
                      repository is stale in that case would be technically true
                      and practically misleading.
    """
    installed = api(f"repos/{ORG}/{repo}/contents/.github/workflows/binding-updater.md")
    if not installed:
        # No agents here, which is not the same as not using the toolbox. Most of
        # the fleet consumes it through reusable workflows -- Meshoptimizer.NET
        # calls five of them -- and reading only the agent pin reported the repo
        # that leans on it hardest as not using it at all.
        #
        # A repository without agents cannot be behind, either: `uses: ...@v1`
        # resolves the tag when the workflow runs, so it is on the current release
        # by construction. Only the compiled agent locks are pinned to a commit,
        # which is the whole reason the drift colouring exists.
        return consumer_state(repo)

    import base64
    import re

    text = base64.b64decode(installed["content"]).decode("utf-8", "replace")
    match = re.search(r"^source:\s*\S+@([0-9a-f]{7,40})\s*$", text, re.MULTILINE)
    sha = match.group(1) if match else None

    version, behind = None, None
    if sha:
        for index, (name, tag_sha) in enumerate(releases):
            if tag_sha.startswith(sha) or sha.startswith(tag_sha):
                version, behind = name, index
                break

    # The `source:` line is rewritten on install, so it always differs. Strip it
    # before comparing; everything else is the workflow the agent actually runs.
    def body(s):
        return "\n".join(l for l in s.splitlines() if not l.startswith("source:")).strip()

    agents_differ = None
    if current_agents:
        agents_differ = body(text) != body(current_agents)

    return {
        "sha": sha,
        "version": version,
        "behind": behind,
        "latest": releases[0][0] if releases else None,
        "agents_differ": agents_differ,
    }


def nuget_latest(package_id):
    """Latest published version and its date, straight from nuget.org."""
    try:
        with urllib.request.urlopen(
            f"https://api.nuget.org/v3-flatcontainer/{package_id.lower()}/index.json", timeout=30
        ) as resp:
            versions = json.loads(resp.read())["versions"]
    except Exception:
        return None, None
    if not versions:
        return None, None
    latest = versions[-1]
    # Versions are date-based (2026.8.1.21), so the version *is* the publish date.
    parts = latest.split(".")
    try:
        published = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)
    except (ValueError, IndexError):
        published = None
    return latest, published.isoformat() if published else None


def audit(run_id, repo):
    """Ask gh-aw for a run's real cost. This is the only source for AI Credits:
    the Actions API knows nothing about them."""
    try:
        proc = subprocess.run(
            ["gh", "aw", "audit", str(run_id), "-j", "-r", f"{ORG}/{repo}", "-o", "/tmp/aw-audit"],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            return None
        return json.loads(proc.stdout)
    except Exception:
        return None


def collect_repo(repo, since, releases, current_agents):
    runs, agent_records = [], []
    for run in api(f"repos/{ORG}/{repo}/actions/runs?per_page=100", paginate=True):
        if run["created_at"] < since:
            continue
        runs.append(run)

    # Pipeline health: the last conclusion per workflow, and whether a failure
    # is sitting there with nobody looking at it.
    pipeline = {}
    for name in PIPELINE_WORKFLOWS:
        matching = [r for r in runs if r["name"] == name]
        if matching:
            newest = max(matching, key=lambda r: r["created_at"])
            pipeline[name] = {
                "conclusion": newest["conclusion"],
                "at": newest["created_at"],
                "url": newest["html_url"],
            }

    # Agent activity. Auditing every run is expensive, so cap it: the dashboard
    # wants a recent trend, not an exhaustive ledger.
    agent_runs = [r for r in runs if r["name"] in AGENT_WORKFLOWS]
    for run in sorted(agent_runs, key=lambda r: r["created_at"], reverse=True)[:40]:
        record = {
            "ts": run["created_at"],
            "repo": repo,
            "agent": run["name"],
            "status": run["conclusion"] or "in_progress",
            "issue": 0,
            "duration_s": 0,
            "iterations": 0,
            "tokens": 0,
        }
        detail = audit(run["id"], repo)
        if detail:
            metrics = detail.get("metrics", {})
            record.update(
                tokens=metrics.get("token_usage", 0),
                iterations=metrics.get("turns", 0),
                credits=round(metrics.get("aic", 0), 2),
                cost=round(metrics.get("aic", 0) * 0.01, 4),
                model=detail.get("engine_config", {}).get("model"),
            )
            overview = detail.get("overview", {})
            try:
                started = datetime.fromisoformat(overview["started_at"].replace("Z", "+00:00"))
                ended = datetime.fromisoformat(overview["updated_at"].replace("Z", "+00:00"))
                record["duration_s"] = (ended - started).total_seconds()
            except Exception:
                pass
        agent_records.append(record)

    # What the agents actually produced, which is the honest measure of whether
    # they are earning their keep.
    prs = api(f"repos/{ORG}/{repo}/pulls?state=all&per_page=100", paginate=True) or []
    agent_prs = [p for p in prs if any(l["name"].startswith("agent:") for l in p.get("labels", []))]
    issues = api(f"repos/{ORG}/{repo}/issues?state=all&labels=agent:needs-human&per_page=50", paginate=True) or []

    manifest = api(f"repos/{ORG}/{repo}/contents/binding.yml")
    package_id, nuget_version, nuget_date = None, None, None
    if manifest:
        import base64
        try:
            import yaml
            data = yaml.safe_load(base64.b64decode(manifest["content"]).decode())
            package_id = data["package"]["id"]
            nuget_version, nuget_date = nuget_latest(package_id)
        except Exception as exc:
            print(f"::warning::{repo}: could not read binding.yml ({exc})")

    # Silent failures are the metric this whole project exists to drive to zero:
    # a red run that nobody, human or agent, has acknowledged.
    open_agent_issues = [i for i in issues if i["state"] == "open"]
    silent = sum(
        1 for name, info in pipeline.items()
        if info["conclusion"] not in ("success", None) and not open_agent_issues
    )

    toolbox = toolbox_state(repo, releases, current_agents)

    return {
        "repo": repo,
        "has_manifest": manifest is not None,
        "toolbox": toolbox,
        # Derived from the installed workflow, not from run history: a repository
        # that has the agents but has not woken them yet still has them. Reading
        # runs made a freshly-installed repo look empty, which is exactly when
        # someone is most likely to be checking.
        # Agents installed, not merely the toolbox consumed. Those are different
        # facts and conflating them is what made the dashboard claim the repository
        # using five reusable workflows was not using the toolbox.
        "has_agents": bool(toolbox) and not toolbox.get("consumer_only"),
        "pipeline": pipeline,
        "package": {"id": package_id, "version": nuget_version, "published": nuget_date},
        "prs": {
            "total": len(agent_prs),
            "merged": sum(1 for p in agent_prs if p.get("merged_at")),
            "open": sum(1 for p in agent_prs if p["state"] == "open"),
            "closed_unmerged": sum(
                1 for p in agent_prs if p["state"] == "closed" and not p.get("merged_at")
            ),
        },
        "open_issues": len(open_agent_issues),
        "silent_failures": silent,
    }, agent_records


def main():
    since = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat()
    releases = toolbox_releases()
    print(f"toolbox releases: {', '.join(n for n, _ in releases[:5])}")

    # The published agent workflow, to tell "a newer release exists" apart from
    # "the agents this repository runs are actually different".
    import base64
    current = api(f"repos/{ORG}/Evergine.Bindings/contents/workflows/binding-updater.md")
    current_agents = base64.b64decode(current["content"]).decode("utf-8", "replace") if current else None

    repos, runs = [], []
    for repo in FLEET:
        print(f"→ {repo}")
        summary, records = collect_repo(repo, since, releases, current_agents)
        repos.append(summary)
        runs.extend(records)

    credits = sum(r.get("credits", 0) for r in runs)
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "org": ORG,
        "window_days": WINDOW_DAYS,
        "repos": repos,
        "runs": sorted(runs, key=lambda r: r["ts"], reverse=True),
        "toolbox_latest": releases[0][0] if releases else None,
        "totals": {
            "repos": len(repos),
            "agents_outdated": sum(
                1 for r in repos
                if r.get("toolbox") and (r["toolbox"].get("behind") or 0) > 0
            ),
            "with_agents": sum(1 for r in repos if r["has_agents"]),
            "with_manifest": sum(1 for r in repos if r["has_manifest"]),
            "agent_runs": len(runs),
            "credits": round(credits, 2),
            "cost": round(credits * 0.01, 2),
            "silent_failures": sum(r["silent_failures"] for r in repos),
            "prs_merged": sum(r["prs"]["merged"] for r in repos),
            "prs_open": sum(r["prs"]["open"] for r in repos),
            "prs_rejected": sum(r["prs"]["closed_unmerged"] for r in repos),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    t = data["totals"]
    print(
        f"\n{t['repos']} repos, {t['with_agents']} with agents, "
        f"{t['agent_runs']} runs, {t['credits']} credits (${t['cost']}), "
        f"{t['silent_failures']} silent failures"
    )


if __name__ == "__main__":
    sys.exit(main())
