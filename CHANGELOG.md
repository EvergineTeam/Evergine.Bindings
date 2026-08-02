# Changelog

All notable changes to the bindings toolbox. Versions follow [Semantic Versioning](https://semver.org/).

Consumers pin the moving major tag (`@v1`). Immutable patch tags (`@v1.0.0`) exist for pinning down a specific release.

## [1.5.1] - 2026-08-02

### Fixed

- **Change detection asks git what would be committed, not what the tree looks like.** Both `binding-tracked-cd` and `binding-xml-cd` used `git status --porcelain`, which compares the working tree against the index and is therefore sensitive to line endings. On a Windows runner, checkout writes CRLF while these files are stored as LF, so every generated file read as modified even when the generator produced byte-identical content.

  The first RenderDoc.NET run made it visible by contradicting itself: detection reported three changed files, and the commit step that followed found nothing to record. Staging first and inspecting `git diff --cached` applies the same normalisation the commit will, so the two can no longer disagree.

  Consequence had it shipped: a NuGet published every month for a binding nobody touched, every job green.

  `binding-xml-cd` carried the same logic. It has not misbehaved because its three repositories run on ubuntu, where nothing rewrites line endings — latent rather than harmless, and fixed alongside.

## [1.5.0] - 2026-08-02

### Added

- **`binding-tracked-cd`** — a CD for bindings that follow an upstream specification. Reads `binding.yml`, fetches whatever it declares through `binding-fetch-upstream`, regenerates, commits sources and generated code together, and publishes only when the generated API changed.

  It is **not specific to any source format**. The adapter handles `http-file`, `git-tree` and `git-submodule`, so the same workflow serves XML registries, C headers and submodules. That is why it is named for the mechanism rather than the format.

  Structurally it is `binding-xml-cd` with the download replaced by the action and the `check_xml` job removed — the action does the comparison inside the build job, and a separate pre-check would have blocked `force-publish`.

### Not changed

- **`binding-simple-cd` is untouched**, verified by diff. It remains correct for the six bindings that ship native binaries built from the same upstream, where regenerating without rebuilding produces a managed layer that does not match the binary it loads. Their manifests say so explicitly.

  An earlier draft added an opt-in `track-upstream` flag to `binding-simple-cd` instead. A separate workflow is better: a flag would have put `if: inputs.track-upstream != true || generated_changed || force-publish` in front of publishing for seven repositories, and a triple negative governing releases is a poor thing to have to review.

### Note

`binding-tracked-cd` makes `binding-xml-cd` redundant — the three XML bindings could migrate by swapping the `uses:` and dropping their `xml-*` inputs, since their manifests already declare the same sources. Deliberately not done here: they work today, and mixing that with proving the new workflow on RenderDoc.NET would make a failure impossible to attribute.

## [1.4.1] - 2026-08-02

### Fixed

- **`binding-fetch-upstream` now runs on Windows.** It hardcoded `python3`, which does not exist on Windows runners, and called `pip` directly rather than `python -m pip`. The action had only ever run on ubuntu — the three XML bindings use the default runner — so this was latent rather than observed. RenderDoc.NET and KTX.NET run on `windows-latest`.

- **Line endings no longer produce phantom changes.** The action compared raw bytes, so a working tree checked out with CRLF against a download arriving as LF reported a change on every run. Nothing would have failed: it would have regenerated, committed and published every month for a file nobody touched. Comparison is now blind to line endings, and writes preserve whichever convention the vendored file already uses, so refreshing a source changes declarations and nothing else.

  `binding-xml-cd` has carried a "Normalize downloaded XML to CRLF" step for exactly this reason. Handling it in the adapter is better: it works regardless of platform, of `core.autocrlf`, and of which convention a given repository happens to use.

## [1.4.0] - 2026-08-02

### Added

- **`force-publish` input on `binding-xml-cd`.** v1.3.0 gated publishing on the generated code changing, which stopped functionally identical packages going out but also blocked the opposite case: an agent opens a pull request containing the regenerated output, a human reviews and merges it, and by the time CD runs there is nothing left to detect. The work sits on the default branch and never reaches nuget.org.

  Found by running it, not by reading it — OpenGL.NET's regeneration merged cleanly and then CD reported "the registry changed but the generated API did not. Nothing to publish."

  The scheduled path keeps the gate exactly as it was. `force-publish` is opt-in on manual dispatch, for shipping something a person has already approved.

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
