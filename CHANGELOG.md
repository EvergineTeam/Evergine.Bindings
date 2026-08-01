# Changelog

All notable changes to the bindings toolbox. Versions follow [Semantic Versioning](https://semver.org/).

Consumers pin the moving major tag (`@v1`). Immutable patch tags (`@v1.0.0`) exist for pinning down a specific release.

## [1.1.1] - 2026-08-02

### Fixed

- **`binding-updater` now installs the .NET SDK before running.** The workflow's whole job is to run a generator and build a binding, and it had no `dotnet` available. It would have reached the build step, found no SDK, and reported a broken generator that was not broken -- a false diagnosis on the one agent allowed to modify generator code. Added as a `steps:` block, which runs deterministically before the agent starts.

Pinned to `actions/setup-dotnet@v5` to match `binding-common-ci.yml` rather than the newer v6, so the agent and CI provision the SDK identically.

## [1.1.0] - 2026-08-02

Adds the first two agentic workflows. Nothing changes for repositories that do not install them.

### Added

- **`workflows/ci-doctor.md`** — reacts to a failed `CI`, `CD` or `Sync standards` run, diagnoses it, and either opens a pull request fixing workflow configuration, re-runs a transient failure once, or files an issue. Model: `claude-sonnet-4.6`.
- **`workflows/binding-updater.md`** — fetches the upstream specification declared in `binding.yml`, regenerates, builds, and fixes the generator when a new upstream construct breaks it. Model: `claude-opus-4.6`.
- **`aw.yml`** — package manifest, so both workflows install with `gh aw add EvergineTeam/Evergine.Bindings/workflows/<name>@v1`.

### Design notes

The two agents divide by *where the fix lives*: anything under `.github/` belongs to the doctor, anything under the generator or its output belongs to the updater. Neither crosses that line.

They hand off through a label rather than a schedule. When the doctor concludes the generator is at fault it files an issue labelled `agent:needs-regen`, and the updater triggers on `issues: [labeled]` as well as on its monthly cron. Without that the diagnosis would sit until the next month; with it, a person can also veto the handoff by removing the label, or force it by adding one.

Both run read-only and write exclusively through `safe-outputs`. Neither can auto-merge: every change is a pull request a person merges.

## [1.0.0] - 2026-08-01

First release. Establishes the toolbox as the single home for everything that automates the bindings fleet.

### Added

- **Reusable workflows** `binding-common-ci.yml`, `binding-simple-cd.yml` and `binding-xml-cd.yml`, copied verbatim from `evergine-standards@v2`. The only change is that they now resolve their composite actions from this repository instead of `evergine-standards`.
- **Composite actions** `binding-generate-bindings-dotnet`, `binding-generate-nugets-dotnet`, `commit-and-push-or-pr-update`, `nuget-publish` and `send-notification-email`, byte-identical copies of their `evergine-standards@v2` counterparts.
- **`binding.schema.json`** — schema for the per-repository `binding.yml` manifest, which declares where a binding's upstream specification lives, how it is fetched and what it publishes.
- **`docs/adapters/`** — one document per upstream adapter (`http-file`, `git-tree`, `git-submodule`) describing how each kind of source is fetched and compared.
- **`metrics/model-rates.json`** — AI Credit rates per model, versioned so historical cost is never recomputed with current prices.

### Notes

- This release changes nothing in the binding repositories. They keep consuming `evergine-standards@v2` until they are repointed one at a time.
- The reusables still expect the PowerShell helpers under `build/scripts/`, which `evergine-standards` continues to distribute through its standards sync. That dependency is deliberate and unchanged.
