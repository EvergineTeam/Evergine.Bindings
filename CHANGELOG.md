# Changelog

All notable changes to the bindings toolbox. Versions follow [Semantic Versioning](https://semver.org/).

Consumers pin the moving major tag (`@v1`). Immutable patch tags (`@v1.0.0`) exist for pinning down a specific release.

## [1.3.0] - 2026-08-02

### Changed

- **`binding-xml-cd` publishes only when the generated code changes, not when the registry does.** A changed `vk.xml` is not a changed API: Khronos reorders elements, fixes typos and edits documentation without touching a declaration, and each of those was producing a functionally identical NuGet. The generated output is the honest signal — if it is byte-identical, nothing worth shipping moved.

- **The registry and the code generated from it are now committed together.** The workflow used to commit the XML *before* running the generator, so the regenerated output was packed, published and discarded. That is why Vulkan.NET's checked-in `Generated/` sat four months behind its own `vk.xml` while every published package was correct: the NuGet was never wrong, the repository was.

  The commit now happens after generation, and `git add -A` picks up both. A registry update with no API change still gets committed — the vendored spec stays current either way — but it is labelled `(no API change)` and publishes nothing.

### Note for consumers

The first run after this lands will produce a large commit in any repository whose `Generated/` has drifted, because it catches up in one go. That is the backlog being paid off, not the workflow misbehaving.

## [1.2.0] - 2026-08-02

Acts on what the first real pilot run measured. It succeeded and cost 46 AI Credits ($0.46), but `gh aw audit` flagged that 93% of its 32 turns were data-gathering a script could do, and that the firewall had blocked a domain the agent then had to reason about.

### Added

- **`binding-fetch-upstream` composite action.** Reads `binding.yml`, fetches every declared source through the adapter named by `upstream.kind`, writes the new content into the working tree, and leaves a one-screen report at `/tmp/gh-aw/agent/upstream-report.md`. Whether a vendored file differs from upstream is a byte comparison; having a model discover that costs turns and reaches the same answer.

  The `git-submodule` adapter deliberately compares the recorded SHA against upstream **without checking anything out**. In KTX.NET a pointer bump means rebuilding native binaries, and in ImGui.Net it means moving four interdependent modules as a compatible set — so that adapter reports and stops.

### Changed

- **`binding-updater` step 2 now reads the report instead of doing the fetching.** The prompt tells it explicitly not to re-download or re-check: the comparison was a hash and is not improved by a second opinion.
- **Opted the dotnet CLI out of telemetry** (`DOTNET_CLI_TELEMETRY_OPTOUT`, `DOTNET_NOLOGO`) rather than adding `dc.services.visualstudio.com` to the firewall allow-list. The agent should not be widening its own network boundary for telemetry.

## [1.1.3] - 2026-08-02

### Changed

- **`binding-updater` runs on `claude-sonnet-5` instead of `claude-opus-4.8`.** Opus resolved correctly but every request came back `429 Too Many Requests` — five retries per attempt, two attempts, then the job timed out having produced nothing. Not a quota or budget problem (`isCAPIQuotaExceededError: false`, `tokenCount: 0`): the model is capacity-constrained through Copilot. A monthly agent that cannot get a response is worth less than a slightly weaker one that runs. Revisit once there is real workload data showing Sonnet struggling.
- **Raised the updater's `timeout-minutes` from the default 20 to 40.** Twenty minutes was too tight regardless of the 429s: downloading a multi-megabyte registry, regenerating, building and reasoning about the diff can legitimately take longer, and pairing a 20-minute ceiling with ~6.5-minute retry cycles meant a failing run burned the entire budget mid-attempt.

## [1.1.2] - 2026-08-02

### Fixed

- **Corrected the model identifiers.** `claude-opus-4.6` and `claude-sonnet-4.6` are rejected at runtime: the AWF binary the compiled workflows run (`0.27.42`) carries a shorter model catalog than the `gh aw` CLI does, so `gh aw compile --strict` accepts a name the runner then refuses. The updater now uses `claude-opus-4.8`, which AWF named itself in its error, and the doctor uses `claude-sonnet-5`.

  Worth knowing for future model changes: compile-time validation does **not** prove a model will resolve at run time. The failure is at least loud and free — AWF rejects the name in the first seconds of the agent step, before any tokens are spent.

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
