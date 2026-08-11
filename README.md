# Evergine Bindings

Hub and automation toolbox for the low-level bindings used in Evergine. This repository does not contain a binding itself: it holds the shared workflows that build, publish and maintain every binding in the fleet, and it tracks their status.

## Toolbox

The reusable workflows and composite actions that every binding repository consumes.

```yaml
# in a binding's .github/workflows/CI.yml
uses: EvergineTeam/Evergine.Bindings/.github/workflows/binding-common-ci.yml@v1
```

| Workflow | Purpose |
|---|---|
| `binding-common-ci.yml` | Build the generator, regenerate the binding, pack the NuGet |
| `binding-simple-cd.yml` | Publish a binding whose specification is vendored in the repository |
| `binding-xml-cd.yml` | Download an XML registry, regenerate and publish |

**Versioning.** Consume the moving major tag `@v1`. Immutable tags (`@v1.0.0`) exist for pinning a specific release. **Never point at a branch** — a branch reference silently drifts and is exactly how a repository ends up running a different pipeline from its siblings without anyone noticing.

See [`CHANGELOG.md`](CHANGELOG.md) for what changed between versions.

### The `binding.yml` manifest

Each binding repository declares, in a `binding.yml` at its root, where its upstream specification lives, how it is fetched and what it publishes. It is the single description that both the deterministic workflows and the agentic ones read.

```yaml
toolbox: 1.0.0
package:
  id: Evergine.Bindings.Vulkan
  project: VulkanGen/Evergine.Bindings.Vulkan/Evergine.Bindings.Vulkan.csproj
upstream:
  kind: http-file
  language: c
  sources:
    - url: https://raw.githubusercontent.com/KhronosGroup/Vulkan-Docs/main/xml/vk.xml
      path: KhronosRegistry/vk.xml
      format: khronos-xml
generator:
  project: VulkanGen/VulkanGen/VulkanGen.csproj
  name: Vulkan
  output: VulkanGen/Evergine.Bindings.Vulkan/Generated
```

`upstream.kind` selects the adapter that knows how to fetch that kind of source:

| Adapter | Used by | How the specification arrives |
|---|---|---|
| [`http-file`](docs/adapters/http-file.md) | Vulkan, OpenXR, OpenGL | A registry file at a stable URL |
| [`git-tree`](docs/adapters/git-tree.md) | WebGPU, RenderDoc, MeshOptimizer, xatlas, Cesium, JoltPhysics | Headers copied from an upstream repository at a pinned tag |
| [`git-submodule`](docs/adapters/git-submodule.md) | KTX, ImGui | A git submodule pointer |

`language` and `format` are deliberately separate. The upstream project may be written in any language while still exposing a C API: JoltPhysics and cesium-native are both C++ (`language: cpp`) surfaced through a C wrapper (`format: c-header`). The binding output is always C#.

The manifest is validated against [`binding.schema.json`](binding.schema.json).

## Current Bindings

The following bindings are currently available in this repository:

### [Vulkan.NET](https://github.com/EvergineTeam/Vulkan.NET)
* Binding for the Vulkan API
* Auto-generated from vk.xml file included in the KhronosRegistry folder

[![CI](https://github.com/EvergineTeam/Vulkan.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/Vulkan.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/Vulkan.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/Vulkan.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.Vulkan?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.Vulkan)

### [OpenXR.NET](https://github.com/EvergineTeam/OpenXR.NET)
* Binding for the OpenXR API
* Auto-generated from xr.xml file included in the KhronosRegistry folder

[![CI](https://github.com/EvergineTeam/OpenXR.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/OpenXR.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/OpenXR.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/OpenXR.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.OpenXR?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.OpenXR)

### [WebGPU.NET](https://github.com/EvergineTeam/WebGPU.NET)
* Lightweight, low-level wrapper built on top of the `wgpu-native` library from Firefox
* Facilitates swift development of an adapter for Evergine, allowing for rapid testing across Windows, Linux, and Mac platforms using DirectX, Vulkan, and Metal

[![CI](https://github.com/EvergineTeam/WebGPU.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/WebGPU.NET/actions/workflows/CI.yml)
[![CD WebGPU](https://github.com/EvergineTeam/WebGPU.NET/actions/workflows/cd.yml/badge.svg)](https://github.com/EvergineTeam/WebGPU.NET/actions/workflows/cd.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.WebGPU?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.WebGPU)

### [OpenGL.NET](https://github.com/EvergineTeam/OpenGL.NET)
* Binding for the OpenGL API
* Auto-generated from gl.xml file included in the KhronosRegistry folder

[![CI](https://github.com/EvergineTeam/OpenGL.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/OpenGL.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/OpenGL.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/OpenGL.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.OpenGL?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.OpenGL)

### [RenderDoc.NET](https://github.com/EvergineTeam/RenderDoc.NET)
* Binding for OpenGL (ES1-3.0, ES2.0, GL 1.x-4.6) and OpenGL ES
* Auto-generated from [renderdoc_api_header](https://github.com/baldurk/renderdoc/blob/v1.x/renderdoc/api/app/renderdoc_app.h "RenderDoc API Header")

[![CI](https://github.com/EvergineTeam/RenderDoc.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/RenderDoc.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/RenderDoc.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/RenderDoc.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.RenderDoc?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.RenderDoc)

### [MeshOptimizer.Net](https://github.com/EvergineTeam/Meshoptimizer.NET)
* Thin low-level autogenerated bindings for MeshOptimizer in C#
* Auto-generated from [Meshoptimizer api header](https://github.com/zeux/meshoptimizer/blob/master/src/meshoptimizer.h)

[![CI](https://github.com/EvergineTeam/Meshoptimizer.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/Meshoptimizer.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/Meshoptimizer.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/Meshoptimizer.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.MeshOptimizer?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.MeshOptimizer)

### [XAtlas.Net](https://github.com/EvergineTeam/XAtlas.NET)
* Thin low-level autogenerated bindings for xatlas in C#
* Auto-generated from [xatlas api header](https://github.com/jpcy/xatlas/blob/master/source/xatlas/xatlas_c.h)

[![CI](https://github.com/EvergineTeam/XAtlas.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/XAtlas.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/XAtlas.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/XAtlas.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.XAtlas?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.XAtlas)

### [ImGui.Net](https://github.com/EvergineTeam/ImGui.Net)
* Thin low-level autogenerated bindings for Imgui in C#
* Includes c# bindings of the most popular imgui libraries as well, Imguizmo, Implot and Imnodes

[![CI](https://github.com/EvergineTeam/ImGui.Net/actions/workflows/ci.yml/badge.svg)](https://github.com/EvergineTeam/ImGui.Net/actions/workflows/ci.yml)
[![CD](https://github.com/EvergineTeam/ImGui.Net/actions/workflows/cd.yml/badge.svg)](https://github.com/EvergineTeam/ImGui.Net/actions/workflows/cd.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.Imgui?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.Imgui)

### [KTX.NET](https://github.com/EvergineTeam/KTX.NET)
* Thin low-level autogenerated bindings for KTX in C#
* Auto-generated from [KTX C header](https://github.com/KhronosGroup/KTX-Software/blob/main/include/ktx.h)

[![CI](https://github.com/EvergineTeam/KTX.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/KTX.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/KTX.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/KTX.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.KTX?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.KTX)

### [Cesium.NET](https://github.com/EvergineTeam/Cesium.NET)
* Low-level bindings for [Cesium Native](https://github.com/CesiumGS/cesium-native) in C#
* Auto-generated from the CesiumNativeC API header

[![CI](https://github.com/EvergineTeam/Cesium.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/Cesium.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/Cesium.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/Cesium.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.CesiumNative?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.CesiumNative)

### [Vuforia.NET](https://github.com/EvergineTeam/Vuforia.NET)
* Low-level bindings for the [Vuforia Engine](https://developer.vuforia.com/) in C#
* Auto-generated from the Vuforia Engine SDK C API

[![CI](https://github.com/EvergineTeam/Vuforia.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/Vuforia.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/Vuforia.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/Vuforia.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.Vuforia?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.Vuforia)

### [JoltPhysics.NET](https://github.com/EvergineTeam/JoltPhysics.NET)
* Low-level bindings for [JoltPhysics](https://github.com/jrouwe/JoltPhysics) (via [JoltPhysicsC](https://github.com/EvergineTeam/JoltPhysicsC)) in C#
* Auto-generated from JoltPhysicsC headers using CppAst

[![CI](https://github.com/EvergineTeam/JoltPhysics.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/JoltPhysics.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/JoltPhysics.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/JoltPhysics.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.JoltPhysics?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.JoltPhysics)

### [MuJoCo.NET](https://github.com/EvergineTeam/MuJoCo.NET)
* Low-level bindings for [MuJoCo](https://github.com/google-deepmind/mujoco) in C#
* Auto-generated from the MuJoCo public headers using CppAst

[![CI](https://github.com/EvergineTeam/MuJoCo.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/MuJoCo.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/MuJoCo.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/MuJoCo.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.MuJoCo?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.MuJoCo)

### [Embree.NET](https://github.com/EvergineTeam/Embree.NET)
* Low-level bindings for [Embree](https://github.com/RenderKit/embree), Intel's ray tracing kernel library, in C#
* Auto-generated from the Embree 4 public headers using CppAst

[![CI](https://github.com/EvergineTeam/Embree.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/Embree.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/Embree.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/Embree.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.Embree?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.Embree)

### [Tracy.NET](https://github.com/EvergineTeam/Tracy.NET)
* Low-level bindings for the [Tracy profiler](https://github.com/wolfpld/tracy) CPU client in C#
* Auto-generated from TracyC.h using CppAst

[![CI](https://github.com/EvergineTeam/Tracy.NET/actions/workflows/CI.yml/badge.svg)](https://github.com/EvergineTeam/Tracy.NET/actions/workflows/CI.yml)
[![CD](https://github.com/EvergineTeam/Tracy.NET/actions/workflows/CD.yml/badge.svg)](https://github.com/EvergineTeam/Tracy.NET/actions/workflows/CD.yml)
[![Nuget](https://img.shields.io/nuget/v/Evergine.Bindings.Tracy?logo=nuget)](https://www.nuget.org/packages/Evergine.Bindings.Tracy)

This README serves as a centralized hub for all the bindings available in this repository. You can find more information about each binding by clicking on the links above.
