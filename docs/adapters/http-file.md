# Adapter: `http-file`

The upstream specification is a single file published at a stable URL. Fetch it, compare it with the vendored copy, and regenerate when it differs.

Used by the registry-driven bindings: **Vulkan.NET**, **OpenXR.NET**, **OpenGL.NET**.

## Manifest shape

```yaml
upstream:
  kind: http-file
  language: c
  project: https://github.com/KhronosGroup/Vulkan-Docs
  version-from: spec-attribute
  sources:
    - url: https://raw.githubusercontent.com/KhronosGroup/Vulkan-Docs/main/xml/vk.xml
      path: KhronosRegistry/vk.xml
      format: khronos-xml
```

## How it is fetched

1. `GET` the `url` of every entry in `sources`.
2. Compare byte-for-byte with the file at `path`.
3. If every source is unchanged, stop and report `noop`. **No model is invoked** — this is a file comparison, not a reasoning task, and it is what keeps the monthly cost near zero for the many months where upstream has not moved.
4. If any differ, write the new content to `path` and continue to generation.

## Determining the upstream version

`version-from: spec-attribute` reads the version out of the document itself, which is more reliable than a tag because the raw URL tracks a branch, not a release:

- **Khronos XML** — the `<type category="define">` entry holding `VK_HEADER_VERSION` (or `XR_CURRENT_API_VERSION` for OpenXR).
- Fall back to `git-release` on `project` when the document carries no version.

## Caveats

- The URL usually points at a **branch** (`main`, `master`), so the content moves under you. Two runs on different days legitimately produce different bytes; that is the normal case, not an error.
- A diff of zero bytes with a changed `ETag` is still a `noop`. Compare content, never headers.
- These files are large — `vk.xml` is several MB. Never load the whole file into a model's context to decide whether it changed. Diff first, and only feed the model the *relevant hunks* plus the generator code.
- Khronos occasionally reorders the document without semantic change. A large textual diff does not imply a large API diff; the API delta must be computed from the parsed model, not from the text.
