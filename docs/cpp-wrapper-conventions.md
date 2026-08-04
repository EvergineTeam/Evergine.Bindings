# Conventions for a hand-maintained C wrapper

The shared half of how EvergineTeam's C wrappers are written. `cpp-wrapper-porter` reads
this, and then reads the repository's own profile for everything this cannot decide.

This document **describes**; it does not authorise rewriting. Anything here that a
repository does differently is that repository's convention, not a defect — see
[Do not enforce this on code you did not touch](#do-not-enforce-this-on-code-you-did-not-touch).

## Where this came from

It was extracted from `EvergineTeam/JoltPhysicsC/.github/agents/cpp-to-c-binding.agent.md`,
which was itself written from CesiumC and then extended with Jolt-specific lessons. That is
why it exists as a shared document: the generalisation had already been done once by hand,
in a file living in one of the two repositories it described, with the other having no copy
at all.

Splitting it also removed a hazard. Several rules in that document contradict CesiumC's
actual code — the overload naming, the converter naming, whether every function body is
wrapped, whether all wrapper structs sit in one file. An agent applying them literally
would have rewritten unrelated files as a side effect of a version bump.

## Layered structure

| | |
|---|---|
| `include/<lib>/` | one public header per domain, plus `common.h` and an umbrella header |
| `src/*_internal.h` | thread-local error state and the exception-translation macros |
| `src/internal.h` | conversions between the C value types and the C++ ones |
| `src/wrappers.h` | internal wrapper structs, in one place, against ODR violations |
| `src/*.cpp` | one per public header |

## Patterns

**Opaque handles.** A C++ object with state or non-trivial layout is a
`typedef struct X X;` in the public header and a `reinterpret_cast` in the implementation.
The C caller never sees the layout.

**Blittable value types.** Small maths types are plain C structs with the same layout,
converted by `static inline` helpers in `internal.h`. Nothing is copied field by field at
the call site.

**Export macro.** `<PREFIX>_API`, `__declspec(dllexport)` or `dllimport` on `_WIN32`
depending on whether `<PREFIX>_EXPORTS` is defined, `__attribute__((visibility("default")))`
elsewhere. Paired with `CXX_VISIBILITY_PRESET hidden` so nothing else escapes.

**Errors.** C++ exceptions do not cross the boundary. Every body is wrapped in the
repository's `TRY_BEGIN`/`TRY_END` pair, which records the message in a thread-local string
readable through a getter. Fallible functions also return a sentinel — zero, identity, or
null — never leaving an out-parameter uninitialised.

**Callbacks.** A function pointer plus `void* userData`, stored in a single-slot field of
the wrapper struct rather than captured in a lambda, so it can be replaced or cleared.

**Collections.** A count and an indexed accessor. Never a raw array with a length the
caller has to trust.

**Null safety.** Handles are checked before the try block, not inside it.

**Ownership.** `_create` and a matching `_destroy`. Anything returned by a query is
borrowed and the caller must not free it; where that is not true, the header says so.

## Rules that do not vary

- Never expose a C++ type — class, template, or STL container — in a public header, and
  never `#include` a C++ header from one. Public headers compile as C11.
- Never duplicate a wrapper struct across translation units.
- Never `const_cast` to mutate through a const pointer.
- Sized integers (`int32_t`, `uint64_t`), not platform-dependent ones.
- A consistent prefix on every public symbol.

## Do not enforce this on code you did not touch

The most important rule, and the one that needs stating because the rest of the document
reads like a mandate.

A version bump is a bounded job: upstream changed something, and the wrapper has to keep
compiling and passing its tests. Bringing the whole file up to convention while you are in
there produces a diff nobody can review, mixes a mechanical repair with a stylistic
argument, and risks changing behaviour in code that was working.

Concretely, in this fleet today: two of CesiumC's implementation files contain no
`TRY_BEGIN` at all, six of its eleven wrapper structs live in `.cpp` files rather than
`wrappers.h`, and its converters are overloaded rather than type-suffixed. All three
contradict this document. None of them is yours to fix during a bump.

If something here is worth applying to existing code, say so in the pull request body and
leave it.

## What the profile decides

This document cannot answer these, and guessing produces plausible-looking wrong code:

| axis | why it varies |
|---|---|
| Identifier scheme | prefix, case, whether a domain segment appears, macro names, whether a boolean typedef exists |
| Overload policy | numeric suffixes (`_Create2`) or semantic ones (`_create_from_url`). Applying the wrong one produces names that read as foreign in that codebase |
| Paths | where headers, sources, tests and the submodule live |
| Scope contract | exhaustive against a reference binding, or deliberately curated with an exclusion list |
| Bump recipe | one submodule pointer, or a pointer plus a dependency baseline plus an explicit library list |
| Test invocation | how to build and run them, and which results mean "skipped" rather than "failed" |
| Pattern modules | reference counting and interface subclassing, or completion callbacks and function-pointer structs. Mutually exclusive in practice |
