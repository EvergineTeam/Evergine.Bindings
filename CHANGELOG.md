# Changelog

All notable changes to the bindings toolbox. Versions follow [Semantic Versioning](https://semver.org/).

Consumers pin the moving major tag (`@v1`). Immutable patch tags (`@v1.0.0`) exist for pinning down a specific release.

## [1.28.0] - 2026-08-08

### Added

- **`notify-downstream`, so a wrapper's release reaches its binding without waiting for a clock.** The two wrapper-binding pairs in the fleet -- `CesiumC` to `Cesium.NET` and `JoltPhysicsC` to `JoltPhysics.NET` -- discover a new release from a monthly cron that fires the day *before* the wrapper's porter agent runs. The binding therefore looks 26 hours too early, and since cutting the release is a manual dispatch on top of that, a version takes two months to reach a package instead of one.

  The action reads a new `downstream:` key from `binding.yml` and sends a `repository_dispatch` of type `upstream-released` carrying the tag, the wrapper and the run id. Who consumes whom is a fact about the project, so it lives in the manifest rather than in a workflow, like everything else the fleet declares.

  `GITHUB_TOKEN` cannot do this — it has no reach outside its own repository. The App can, and needs no new secret: `APP_CLIENT_ID` and `APP_PRIVATE_KEY` are already organisation-wide with visibility `all`. What differs from every other mint in this fleet is the scoping, since those all narrow the token to the repository doing the minting, explicitly or by omission. Confirmed before writing any of this by minting a token from CesiumC scoped to Cesium.NET and having the dispatch accepted.

  A manifest with no `downstream:` key is not an error, but it says so in the log: "nothing happened" and "nothing was meant to happen" are otherwise indistinguishable. A destination outside the owner is refused rather than quietly widening what the App is asked for. And a dispatch that fails fails the step, after trying the rest — a notification that does not arrive and does not say so is worse than none, which is what `nuget-publish` taught this week.

## [1.27.0] - 2026-08-08

### Fixed

- **`nuget-publish` now fails when the push fails, and checks the list it actually publishes.** Two defects, neither of which broke a run, both able to break one silently.

  The nuget.org branch never checked `$LASTEXITCODE` while the Azure Artifacts branch checked it twice, so a failed push to nuget.org relied on the exit code propagating out of pwsh unaided. `$ErrorActionPreference = 'Stop'` does not cover that: it governs PowerShell cmdlet errors, not the exit codes of native executables. Publishing is the worst place to report success without having done anything.

  And the guard validated a different file list from the one it guarded. It listed `*.nupkg` with the pattern hardcoded, then handed `Join-Path $packagesFolder $packagePattern` to NuGet, so it confirmed that packages existed and something else was uploaded. It happened to agree, because NuGet expands the glob it is given, but a guard built that way cannot catch the mismatch it exists for. Both now come from one resolution, and the push receives resolved paths rather than a pattern, so the log names exactly what went up.

  `-Filter` is the Win32 FindFirstFile matcher and understands neither `**` nor path separators, so the default `**/*.nupkg` is normalised to a filter plus `-Recurse`, and a pattern that still contains a separator is rejected outright rather than silently matching nothing.

## [1.26.0] - 2026-08-07

### Added

- **The three CD workflows upload the packed `.nupkg` as a run artifact.** `publish-enabled: false` already existed and already skipped the push, but the packages it built were listed and then discarded, so the option could confirm that packing worked and nothing more. Installing a package to try it meant publishing it first, and nuget.org is not a staging area: a version pushed there cannot be withdrawn, only unlisted.

  Uploaded on every run rather than only when publishing is off. When a publish does go out, the artifact is the only copy of exactly what was pushed, which is what you want in hand when a consumer reports something the sources do not explain.

  Applied to `binding-tracked-cd`, `binding-simple-cd` and `binding-xml-cd`, which all had the same gap.

## [1.25.0] - 2026-08-05

### Added

- **`release.track: tags`, for upstreams that tag and never cut a release.** `stable` reads `releases/latest` and `latest` reads `releases?per_page=1`; both answer 404 or empty for a repository that only tags. CesiumGS/cesium-native is one -- sixty-odd tags, **zero** published releases -- so neither existing track can follow it at all, and CesiumC had no way to answer "has upstream moved?" with the shared machinery.

  Resolution is by parsed version rather than by the order the API returns, because GitHub documents no order for the tags endpoint: taking the first would make the answer depend on something nobody controls and change under us with no upstream change. Tags carrying a prerelease or build suffix are skipped, which makes this the tag-only equivalent of `stable` rather than of `latest`. Paginated to ten pages, and it warns rather than answering from a subset if an upstream ever exceeds that.

  Verified against both kinds of repository: `CesiumGS/cesium-native` resolves to `v0.63.0`, and `jrouwe/JoltPhysics` resolves to `v5.6.0` -- the same answer its `track: stable` gives, so the two agree wherever both are usable.

  The cost is worth naming: with `stable` the upstream author decides what counts as newest, and here we decide by parsing version strings. That is strictly worse information, and it is the only information a tag-only upstream offers.

## [1.24.1] - 2026-08-05

### Fixed

- **`wrapper-submodule-bump.yml` was not valid YAML, and had never been.** Its `field()` helper was written as a multi-line `python -c` whose continuation lines sat at column 0 -- which ends a YAML block scalar. The file stopped parsing as a workflow, so GitHub attributed a failed empty run to every push to `main`: ten of them before anybody noticed the notifications. It also means the pointer bump this workflow exists to perform could never have run, so `cpp-wrapper-porter`'s pull-request delivery path was broken rather than merely untested. Collapsed to one line. The comment that used to sit above it congratulated itself on avoiding a nesting trap while sitting inside a different one.

  Only this workflow was affected: the other ten parse, and the top-level `description` key nine of them carry is tolerated rather than invalid -- they have zero runs of their own because `workflow_call` workflows execute in the consumer's repository.

## [1.24.0] - 2026-08-05

### Added

- **`native_paths.py`, and `package.natives` in the manifest, so an Apple framework can be checked.** Vuforia.NET ships two platforms and the coherence tools could see one: its iOS payload is a `.framework` staged under `buildTransitive/ios/` for consumers, which is outside `runtimes/` and is a directory rather than a file. The glob never reached it, the extension filter would have skipped it, and `check-native-arch.py` handed the directory to `read_bytes()`, which raises with no diagnostic. So that platform went unchecked and `native-coherence` had to stay off -- 495 P/Invokes with half the package unverified. Discovery now lives in one shared module used by both checkers, resolves a framework bundle to the binary inside it (flat iOS layout and versioned macOS layout), and takes extra paths from `package.natives` where the convention cannot carry the RID.

### Changed

- **The coherence check accepts a library named by an expression.** It required a quoted literal, and Vuforia.NET generates `[DllImport(Native.Dll, ...)]` -- a const that is the library name on Android and `"__Internal"` on iOS, where the library is linked into the app. All 495 declarations matched nothing and the check died claiming the bindings had not been generated. `library_matches` is gone with it: nothing pairs a name with a file any more, and it could never have done so for a name that refers to the consuming application.

- **A declared symbol must resolve in at least one shipped library, not in every one.** A package whose managed surface is the union of several platforms cannot satisfy "every symbol everywhere" and should not be asked to: Vuforia declares four ARKit functions and three ARCore ones, and each library exports one set and not the other. Measured on the shipped binaries: 495 declarations, 3 absent from iOS, 4 absent from Android, none absent from both. The per-platform gaps are now reported without failing, because a count that grows unexpectedly after an upstream refresh is the signal.

  What this gives up, stated rather than found out later: a function that ought to exist on both platforms and only exists on one now passes. Catching that would mean teaching the check which platform each declaration belongs to, which couples it to how one generator emits `#if` guards.

  **The guarantee that every shipped platform was actually read is kept separate and intact.** It is the property that caught JoltPhysics.NET shipping ten libraries with three passing unexamined, and relaxing the symbol comparison must not be able to take it with it. It also now counts platforms whose files failed to resolve, which the first cut of this change did not -- a platform whose only file cannot be read has to be nameable, and building the set from resolved entries alone made it invisible.

- **`macho_arch` handles universal binaries.** It read the field at offset 4 as a cputype; in a fat binary that is the count of architectures, so `MACHO_CPU` returned nothing and the file was reported unreadable -- a fat binary looked like a corrupt one. Every Apple payload in this fleet happens to be thin today, which is luck rather than a property.

## [1.23.0] - 2026-08-04

### Added

- **`kind: vendored`, for an upstream no machine can fetch.** The Vuforia Engine SDK is only downloadable after signing in to developer.vuforia.com and accepting the EULA, so its headers arrive by hand and live in the repository. Without this, such a repository is locked out of `binding-tracked-cd` -- the only CD here that commits regenerated output -- because every other kind either fetches or fails, and `publish-only` skips the fetch by also skipping the commit, which is the opposite of what is wanted. The adapter downloads nothing, writes nothing, checks that the declared sources are present, and reports whether the generated code has caught up. See `docs/adapters/vendored.md`.

  `changed` stays `false` on every run, deliberately: nothing was brought in by the step, since the sources were committed by whoever dropped them there alongside any native binaries from the same archive. Reporting `true` would trip the tracked CD's refusal to commit a source bump with no matching native rebuild -- a refusal that has caught a real defect and simply does not apply here. The publish decision therefore rests on the generated delta, which is where it belongs.

- **`upstream.version-probe`, so a vendored version is read rather than maintained.** There is no tag to resolve and no release API to ask, so the version is a fact about the committed files. The probe reads it out of them and writes it into `release.current`, which means refreshing the sources updates the manifest in the same commit and the two cannot drift. Several patterns are allowed because a version is not always written in one place -- Vuforia spells it as three separate `#define`s -- and each must match **exactly once**. Zero matches is an error rather than a fall back to the recorded value: the file changed shape, and a silent miss would report the stale version for as long as nobody looked.

  It also makes resolve-only mode useful for these repositories. With `track: pinned` and nothing else, resolve-only echoed the manifest's own recorded value back and could never notice that the tree had moved past it.

### Changed

- **`binding-updater` no longer treats "nothing changed" as the whole answer for a vendored upstream.** The report says nothing changed on every run, by construction, so the existing absolute rule would have made the agent noop even when it had been woken by `agent:needs-regen` to repair a failed regeneration. Now what woke it decides: a schedule is a noop, because it cannot chase a bump it cannot download, while the label is its case and everything it needs is already in the working tree. It is also told not to propose a script that downloads the upstream, since that download is gated on a person accepting a licence.

## [1.22.0] - 2026-08-04

### Added

- **`wrapper-submodule-bump`, so `cpp-wrapper-porter` can deliver a pull request.** gh-aw cannot push a submodule bump: its signed-commit path builds commits through the GitHub API, which has no way to write a gitlink, and it refuses the unsigned fallback whenever a submodule has moved. The porter's first real run did the whole job -- found the API break in JoltPhysics 5.6.0, repaired it, ran 259 tests green -- and could only report it as an issue. The work was right; the delivery was impossible. Now the agent records the release it is taking in `upstream.release.current` and restores the pointer before finishing, and this workflow reads that field on the pull request branch and moves the pointer to match. Judgement to the agent, mechanical movement to a workflow.

### Changed

- **`cpp-wrapper-porter` no longer tries to commit the submodule.** It checks the release out locally to build against, records the tag in the manifest, and restores the recorded gitlink before emitting. A patch containing a submodule change is not merged with a warning -- the whole pull request degrades into an issue and the work is stranded.

### Note

`wrapper-submodule-bump` requires a GitHub App rather than `GITHUB_TOKEN`, for a reason easy to miss: **a push made with `GITHUB_TOKEN` does not trigger workflows.** The submodule commit would land and the build would never re-run, leaving a pull request that looks unverified because nothing verified it.

## [1.21.1] - 2026-08-04

### Fixed

- **`cpp-wrapper-porter` asked for a model the runtime does not know.** `claude-opus-5` is rejected outright by this AWF version, which suggests `claude-opus-4.8` — while accepting `claude-sonnet-5`, which the other two agents use. The reasoning for an Opus-class model here is unchanged; only the identifier was wrong. Worth recording that `gh aw compile --strict` accepted the bad name and the failure came at run time, so a model name is not validated when the lock file is built.

## [1.21.0] - 2026-08-04

### Fixed

- **`toolbox-updater` no longer deletes a repository's own `.github/agents/`.** It removed the whole directory to clear the authoring scaffolding `gh aw add` regenerates, which would have taken JoltPhysicsC's `cpp-to-c-binding.agent.md` with it — twelve kilobytes of conventions the repository owns, in a directory the installer also writes to. It had never mattered because no repository had put anything of its own there; it would have gone quietly the first week one did. Now it deletes the installer's file by name and removes the directory only if that leaves it empty.
- **`binding-updater` stops silently where there is no `generator` block.** Same rule as `cpp-wrapper-porter`: an agent installed as a package arrives everywhere, and reporting on a repository it cannot act on is noise once per repository per month.

### Note

The rule this settles is worth stating: **an agent shipped in the package must be inert where it does not apply.** `ci-doctor` had that property by accident, through a trigger naming specific workflows. Both others now have it deliberately.

## [1.20.1] - 2026-08-04

### Fixed

- **`cpp-wrapper-porter` is inert where it does not belong.** Agents are installed as a package, so it arrives in every repository the toolbox serves — and almost none are hand-written wrappers. It now stops silently when the manifest has no `wrapper:` block, and opens an issue only when a repository claims to be a wrapper and then fails to say how. `ci-doctor` already had this property through its trigger naming specific workflows; this makes it a rule rather than an accident, because an agent that files an issue wherever it does not apply produces one piece of noise per repository per month, which is how a real signal gets ignored.

## [1.20.0] - 2026-08-04

### Added

- **`cpp-wrapper-porter`, a third agent, for the two repositories with no generator.** `JoltPhysicsC` and `CesiumC` are hand-written C wrappers over C++ libraries; when upstream cuts a release somebody reads what changed and edits C. The mandate is deliberately narrower than "update the wrapper": repair what the release broke, and report what it added as a proposal. It does not diff upstream's headers — between Jolt 5.5.0 and 5.6.0 that is 155 headers and four thousand lines of mostly internal change — it moves the pointer and compiles, so the errors are exactly the subset that touches the wrapper. Runs on Opus, because a mistake here is C++ that compiles.
- **`docs/cpp-wrapper-conventions.md`,** the shared half of how these wrappers are written, and `wrapper.profile` in the manifest for the half that varies: identifier scheme, overload policy, scope contract, bump recipe, test invocation. Extracted from `JoltPhysicsC/.github/agents/cpp-to-c-binding.agent.md`, which had been written from CesiumC and lived in the other repository. Splitting it removed a hazard: several of its rules contradict CesiumC's actual code, so an agent enforcing them literally would have rewritten unrelated files during a version bump. The shared document now states that it describes rather than mandates.

## [1.19.0] - 2026-08-04

### Added

- **`binding-upstream-drift`, a CI check that the tree matches the release it claims.** CI and the CD were not reading the same thing: CI regenerates from the sources vendored in the repository, the CD fetches them from the tracked release first. While those agree the distinction is invisible; once they diverge, CI goes green over one revision while the CD publishes another. JoltPhysics.NET vendored headers from `main` while recording v5.5.0, every pull request passed, and the first CD after release tracking committed C# that did not compile.
- **`at-recorded-release` on `binding-fetch-upstream`.** Fetches at `release.current` rather than the newest release, which is what turns a fetch into a drift check. Answering "does the tree match what it claims?" instead of "has upstream moved?" is deliberate: a newer release is news, a tree disagreeing with its own recorded revision is a defect, and only the second should fail a pull request.

## [1.18.1] - 2026-08-04

### Fixed

- **Native coherence reads static archives, and stops calling a partial check complete.** It skipped every extension it did not recognise, silently, then reported success over the remainder — seven platforms of ten for JoltPhysics.NET, with the three `.a` archives passing unexamined while the summary read "all 7 shipped libraries". Those three are the worst to lose: they are static libraries because those platforms cannot load a shared one, so nothing else exercises them either. Symbols now come from the archive's own index, which is what makes WebAssembly work without decoding wasm objects. The check also compares the runtime identifiers it verified against the ones the package ships and fails naming any it missed.

## [1.18.0] - 2026-08-04

### Added

- **Native libraries can come from release assets.** `upstream.assets` downloads binaries attached to the release the sources came from and unpacks them, for a binding whose libraries are built in another repository. `natives-artifact-pattern` covers the case where the CD builds them in the same run; nothing covered this one. Cross-repo artifacts expire and record no version — all 42 that JoltPhysicsC had produced were already gone — and calling the other repository's build as a reusable workflow cannot follow a resolved tag, because `uses:` takes no expression. Defaulting the tag to the resolved release is what keeps headers and libraries on one revision by construction.
- **A third agent, `cpp-wrapper-porter`,** registered in the manifest schema. For repositories with no generator, where a version bump becomes compile errors somebody has to resolve.

### Changed

- **The tracked CD's native backstop accepts either route.** It refuses to commit a source bump for a package shipping native binaries unless the binaries were handed over — correct, and what stopped ImGui.Net publishing 24 symbols exported by nothing — but it knew only artifacts, so it would have refused a release-asset binding for doing the right thing.
- **The manifest requires only `toolbox` and `upstream`,** with `package` and `generator` required together. A repository that tracks an upstream but publishes no package can now carry a manifest and reuse release resolution instead of reimplementing it.

### Fixed

- **Archive member names are parsed as POSIX.** The first traversal guard used `Path(entry).is_absolute()`, which is `False` on Windows for `/etc/passwd` — no drive letter — and joining a rooted path discards the left side, so the entry landed outside the destination. Effective on Linux, useless on the runner the feature exists for.

## [1.17.0] - 2026-08-03

### Added

- **`publish-only` on the tracked CD.** Packages and publishes the repository as it stands, without consulting upstream. `force-publish` still fetches first, so once upstream moves it ships the newer sources rather than the reviewed ones — the same input meaning two different things. Refuses to run if regeneration would change the tree, since that would publish something `main` does not contain.

## [1.16.1] - 2026-08-03

### Fixed

- **The API surface dumper survives references it cannot resolve.** It aborted with SIGABRT on an unresolvable `Evergine.Mathematics`. Degrading alone would have given a green verdict with 11% of the surface opaque, which is worse than the crash, so the build also stops creating them via `CopyLocalLockFileAssemblies`.

## [1.16.0] - 2026-08-03

### Added

- **`submodule_heads`, so a native build compiles the revision the run will commit.** The build was checking out the *recorded* pointers, which are the old ones when a bump is imminent. Artifacts arrived, every gate passed, and the package was equally broken — the dangerous shape, because nothing looked wrong.

## [1.15.2] - 2026-08-03

### Fixed

- **`resolve-only` never inspected submodules.** It computed `ref_moved` from the release block alone, so a submodule manifest always reported nothing moved, the native build was skipped, and the CD committed a bump against old libraries.

## [1.15.1] - 2026-08-03

### Added

- **`checkout-submodules` on the tracked CD.** Moving a submodule pointer means fetching inside it, and there is nothing to fetch in if it was never checked out.

## [1.15.0] - 2026-08-03

### Added

- **An architecture check for every shipped library.** Reads PE, ELF, Mach-O and `ar` directly and compares the machine field against what the RID promises. ImGui.Net published an `osx-x64` dylib that was arm64. Unreadable counts as a failure, not a pass.

## [1.14.0] - 2026-08-03

### Added

- **A freshness check for exported definitions,** byte-comparing each vendored copy against its submodule source.

### Fixed

- **The coherence check reads imports with no `EntryPoint`.** It required one, so for a binding that lets the method name be the symbol it validated 15 declarations out of 612 and reported green.

## [1.13.0] - 2026-08-03

### Added

- **`bump: together` and `exports` for submodules.** All heads resolve before anything moves, so a set of submodules compiling into one binary never lands a combination upstream never built; `exports` copies generated definitions out of the submodule, which used to be a manual step nothing failed over.

## [1.12.0] - 2026-08-03

### Added

- **The API gate's merge depends on native coherence.** Run as a separate workflow it would go red while the merge proceeded anyway.

### Fixed

- **The dashboard stopped reporting toolbox consumers as not using the toolbox.**

## [1.11.3] - 2026-08-03

### Fixed

- **`toolbox-updater` reads one SHA, not one per installed workflow.** `grep -hm1` counts per file, so two installed workflows produced two lines and the comparison could never match — it would have reported every repository outdated forever.

## [1.11.2] - 2026-08-03

### Fixed

- **The API gate clears the `api:breaking` label when the verdict turns additive.** It set the label and never removed it.

## [1.11.1] - 2026-08-03

### Added

- **`exempt-symbols` on the API gate,** for the version constant upstream bumps every release. Meshoptimizer's `VERSION = 1000` becoming `1020` was reported as a removal, so every release looked breaking.

## [1.11.0] - 2026-08-03

### Added

- **A coherence check that every P/Invoke resolves in the shipped native libraries.** P/Invoke binds late: a declaration naming a symbol the library does not export compiles, passes CI, publishes, and throws on the first call.

## [1.10.0] - 2026-08-03

### Added

- **`natives-artifact-pattern` on the tracked CD,** unpacking binaries built earlier in the same run before the change is detected, so the libraries and the header they were built from land in one commit.
- **A format-aware exported-symbol dumper,** replacing `nm`/`dumpbin` scraping that reported a library's own name as a symbol.

## [1.9.0] - 2026-08-03

### Added

- **Release tracking.** `upstream.release.track` follows `stable`, `latest` or stays `pinned`, for bindings that must not chase a branch.

### Fixed

- **The `paths` output, advertised since 1.2.0 and never written.** Callers received an empty list and counted every fetched source as a generated change, publishing a package whenever upstream moved even when the API was identical.

## [1.8.1] - 2026-08-02

### Fixed

- **The API gate clears the build output between the two sides,** which it was otherwise comparing against itself.

## [1.8.0] - 2026-08-02

### Added

- **The API gate.** Measures what a pull request does to the public API surface and merges automatically when nothing anyone can notice changed. Enum and constant *values* are part of the measured surface, because a renumbering keeps compiling and sends the wrong number to the driver.

## [1.7.1] - 2026-08-02

### Fixed

- **`ci-doctor` can open pull requests again.** `protected_files_policy: request_review` cannot be honoured on the signed-commit path, so the doctor degraded to an issue instead of proposing the fix.

## [1.7.0] - 2026-08-02

### Added

- **`ci-doctor` can now open the pull requests it is for.** With a GitHub App configured, `allow-workflows: true` grants the `workflows` permission that `GITHUB_TOKEN` cannot hold. Until now the doctor could diagnose a broken workflow and then fail to propose the fix, degrading to an issue with a manual link — the one thing it exists to do, blocked by the one permission it needed.

### Changed

- **`toolbox-updater` uses the App instead of a personal token.** It previously required a `WORKFLOW_TOKEN` secret with `workflow` scope. An installation token is better on every axis that matters here: owned by the organisation rather than by a person, valid for an hour rather than a year, and it does not stop working when whoever created it changes role.

### Note on scope

Only `ci-doctor` and `toolbox-updater` use the App. `binding-updater` writes to the generator and its output, never to `.github/workflows/`, so it keeps the default token — the smaller permission is the correct one for it.

## [1.6.0] - 2026-08-02

### Added

- **`toolbox-updater`** — keeps a binding's installed agents pinned to the current release. Compares the `source:` recorded in the installed workflows against the latest tag, and when they differ reinstalls, recompiles and opens a pull request.

  Moving the `v1` tag updates nothing on its own: a repository keeps the commit it was compiled against until something recompiles it, and nothing fails in the meantime. Three of the four piloted repositories had already drifted four releases behind without a single red run.

  **Deliberately not an agentic workflow.** Comparing two versions, running `gh aw add --force` and recompiling is entirely deterministic; there is nothing for a model to decide and inference would be waste. The original design had it as an agent — that was wrong on cost, and it also turns out to be impossible: `GITHUB_TOKEN` cannot hold the `workflows` permission, so an agent's `create-pull-request` cannot touch `.github/workflows/` without a configured GitHub App.

### Fixed

- **`has_agents` is derived from the installed workflow rather than from run history.** A repository with the agents installed but not yet woken counted as having none — which is exactly the moment someone is most likely to look. RenderDoc.NET showed as agent-free minutes after being set up.

### Known limitation

`ci-doctor` restricts its pull requests to `.github/workflows/**`, which is precisely what `GITHUB_TOKEN` may not write. Its pull request creation will fail and fall back to an issue containing a one-click link to open the change manually. Diagnosis still lands; the fix needs one click instead of none. Configuring `safe-outputs.github-app` in the toolbox removes the limitation for every repository at once.

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
