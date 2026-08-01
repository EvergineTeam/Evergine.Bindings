# Adapter: `git-submodule`

The upstream project is wired in as a git submodule. Nothing is copied: the specification is read straight out of the checked-out submodule, and "updating" means moving the submodule pointer.

Used by **KTX.NET** (`KhronosGroup/KTX-Software`) and **ImGui.Net** (`cimgui`, `cimguizmo`, `cimplot`, `cimnodes`).

## Manifest shape

```yaml
upstream:
  kind: git-submodule
  language: c
  project: https://github.com/KhronosGroup/KTX-Software
  version-from: submodule-sha
  sources:
    - repo: KhronosGroup/KTX-Software
      path: KTX-Software              # the submodule mount point
      format: c-header
```

`path` is the submodule mount point, not a file. Which headers inside it feed the generator is the generator's business, not the adapter's.

## How it is fetched

1. Resolve the submodule's currently recorded SHA from the index (`git ls-tree HEAD <path>`), without checking it out.
2. Resolve the upstream default branch's head SHA, or the latest release tag when `version-from: git-release`.
3. Equal → `noop`, no model invoked.
4. Different → check out the submodule at the new SHA and continue to generation.

Reading the recorded SHA from the index means the comparison costs one API call and no clone. Only when there is genuinely something to do does the workflow pay for `--recurse-submodules`.

## What makes this adapter different

**The submodule pointer is part of the repository's own history.** Bumping it is a real commit that changes what the binding is built against, and for these two repos it is entangled with native artifacts:

- **KTX.NET** builds native libraries from the submodule (`build_native_libs.py`, `cmake/`, a dedicated *Build native libs* workflow). A pointer bump means the natives must be rebuilt and republished; regenerating only the C# side produces a managed layer that does not match the shipped binary.
- **ImGui.Net** carries four independent submodules that must stay mutually compatible — `cimgui` and `cimplot` pinned to versions built against different Dear ImGui releases will compile and then misbehave at runtime.

Consequences for the agent:

- A submodule bump is **always** a separate pull request, labelled `needs-human-review`, never bundled with anything else.
- For multi-submodule repositories the agent must not bump one in isolation. Either all move together to a compatible set, or it files `agent:needs-human` and stops.
- If a native build step exists, the pull request is not proposable until that build is green.

Of the three adapters this is the one where doing nothing is most often the right answer. Prefer reporting over acting.

## Caveats

- `version-from: submodule-sha` gives a SHA, which is exact but unreadable. When the upstream publishes releases, prefer `git-release` and record the tag in the pull request body so the history says *v4.3.2*, not a hex string.
- Shallow clones do not carry submodule information. Any workflow using this adapter must check out with `submodules: recursive` before the generation step.
