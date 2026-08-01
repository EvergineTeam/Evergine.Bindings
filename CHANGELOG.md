# Changelog

All notable changes to the bindings toolbox. Versions follow [Semantic Versioning](https://semver.org/).

Consumers pin the moving major tag (`@v1`). Immutable patch tags (`@v1.0.0`) exist for pinning down a specific release.

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
