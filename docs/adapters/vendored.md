# Adapter: `vendored`

The upstream cannot be fetched by a machine, so it lives in the repository. This adapter downloads nothing and writes nothing; its job is to read the version out of the sources somebody committed and report whether the generated code has caught up.

Used by **Vuforia.NET**, whose SDK is only downloadable after signing in to developer.vuforia.com and accepting the EULA.

## Why it exists

Without it, such a repository is locked out of `binding-tracked-cd` — the only CD in this toolbox that commits regenerated output. It requires a manifest and it runs the upstream adapter, and every other kind either fetches or fails: `http-file` with an unfetchable URL aborts the step, and `publish-only` skips the fetch by also skipping the commit, which is the opposite of what is wanted.

So this is not a way to describe an upstream we are ignoring. It is a way to say: the sources arrive by hand, on purpose, and everything downstream of them is still automated.

## Manifest shape

```yaml
upstream:
  kind: vendored
  language: c
  project: https://developer.vuforia.com/downloads/sdk

  version-probe:
    file: VuforiaGen/Headers/VuforiaEngine/VuforiaEngine.h
    patterns:
      - 'define\s+VU_VERSION_MAJOR\s+(\d+)'
      - 'define\s+VU_VERSION_MINOR\s+(\d+)'
      - 'define\s+VU_VERSION_PATCH\s+(\d+)'
    join: '.'

  release:
    track: pinned
    current: 11.4.4

  sources:
    - path: VuforiaGen/Headers
      format: c-header
```

## What it does

1. Check that every declared `sources[].path` exists. It cannot be fetched, so its absence is a defect rather than something to fix by downloading.
2. Read the version with `version-probe` and emit it as `resolved_ref`.
3. Compare it against `release.current`. If they differ, somebody refreshed the sources: write the probed version into the manifest and say that the generated code needs to catch up.
4. Emit `changed=false` regardless.

## `changed` is always false, and that is deliberate

`changed` means "this step brought something in". Nothing was brought in — the sources were already committed by whoever dropped them there, in the same commit as any native binaries that came out of the same archive.

Reporting `true` would trip `binding-tracked-cd`'s refusal to commit a source bump for a package that ships natives without a matching native rebuild. That refusal is right to exist and has caught a real defect; it simply does not apply here, because the human committed the sources and the binaries together and there is nothing for CI to rebuild.

The consequence to understand: **the publish decision rests on the generated delta, not on this flag.** Refreshed sources that regenerate to identical code publish nothing, unless the manifest edit or new binaries moved the tree — which they will have, since new binaries are the reason the version changed at all.

## `version-probe`

There is no tag to resolve and no release API to ask, so the version is a fact about the files rather than a number anybody maintains. Reading it from the sources means refreshing them updates the manifest in the same commit, and the two cannot drift.

Every pattern must match **exactly once**. Zero is an error, not a fall back to the recorded value: the file changed shape, and a silent miss would report the stale version for as long as nobody looked. More than one is also an error, because taking the first would be a guess.

Several patterns are allowed because a version is not always written in one place. Vuforia spells it as three separate `#define`s.

## Caveats

- **Nothing verifies that the vendored sources and the shipped binaries agree.** They came out of the same archive, so they do — but that is trust in whoever committed them, not a check. `binding-native-coherence` is the closest thing, and it only proves the P/Invokes resolve.
- **Noticing a new upstream version is somebody else's job.** This adapter reads what is in the tree; it has no idea what upstream has published. Vuforia.NET carries a local `release-watch.yml` that scrapes the release notes and opens an issue, because there is no feed to subscribe to.
- **Do not propose a script that downloads the upstream.** For the case this adapter was built for, the download is gated on accepting a licence. That is a human act, and automating around it is not a technical improvement.
