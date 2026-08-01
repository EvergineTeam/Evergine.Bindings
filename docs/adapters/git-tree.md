# Adapter: `git-tree`

The upstream specification is one or more files living inside another repository, copied into this one rather than referenced as a submodule. Read them from a pinned ref, compare, and regenerate when they differ.

Used by the C-header bindings: **WebGPU.NET**, **RenderDoc.NET**, **Meshoptimizer.NET**, **xatlas.NET**, **Cesium.NET**, **JoltPhysics.NET**.

These six share an identical generator skeleton — `CsCodeGenerator.cs`, `Headers/`, `Helpers.cs`, `Program.cs` — so one adapter and one agent prompt cover all of them without branching.

## Manifest shape

```yaml
upstream:
  kind: git-tree
  language: rust                  # wgpu-native is Rust; it exposes a C API
  project: https://github.com/gfx-rs/wgpu-native
  version-from: git-release
  sources:
    - repo: gfx-rs/wgpu-native
      ref: v25.0.2.1              # pinned on purpose, see below
      remote-path: ffi/wgpu.h
      path: WebGPUGen/WebGPUGen/Headers/wgpu.h
      format: c-header
```

## How it is fetched

1. Read `remote-path` from `repo` at `ref` through the GitHub contents API. No clone: these are a handful of headers, not a tree.
2. Compare with the local `path`.
3. Unchanged → `noop`, no model invoked.
4. Changed → write and continue to generation.

## Why `ref` is pinned to a tag

This is the difference that matters against `http-file`. A C header is a *contract*: taking it from `main` means the binding can silently drift ahead of the shipped native library, and the managed struct layout stops matching the binary users actually load. Getting that wrong produces memory corruption at runtime, not a build error.

So `ref` names a **release tag**, and moving it is a deliberate act:

- The agent may propose a bump to a newer tag, but it opens it as a separate, clearly-labelled pull request.
- The bump and the regeneration land together, never apart.
- If the native library is distributed as a NuGet or a binary artifact, the tag must match the version of that artifact. Verify it before proposing the bump.

## Caveats

- **Headers are not self-describing.** There is no version attribute inside `wgpu.h`; the version *is* the tag. `version-from: git-release` is therefore the only sound option here.
- Several sources may come from different repositories — ImGui-style projects split across `cimgui`, `cimplot`, and so on. Each entry in `sources` carries its own `repo` and `ref`.
- A header that only gains comments or reorders declarations still produces a textual diff. Compare the parsed declarations, not the raw text, before claiming the API changed.
