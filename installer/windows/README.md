# Windows Installer Layout

This folder contains Inno Setup specs and build scripts for MIDORI Windows installers.

## Build Scripts

- `build-installer.ps1`: base builder (defaults to `midori-v0.1.0.iss`).
- `build-installer-v0.1.0.ps1`: explicit `0.1.0` installer build script.
- `build-installer-v0.2.0.ps1`: explicit `0.2.0` installer build script.
- `build-installer-v0.2.1.ps1`: explicit `0.2.1` installer build script.
- `build-installer-v0.2.2.ps1`: explicit `0.2.2` installer build script.
- `build-installer-v020.ps1`: compatibility shim that forwards to `build-installer-v0.2.0.ps1`.
- Build scripts validate installer assets and do not rewrite tracked icon files during build.

## Setup Specs

- `midori-v0.1.0.iss`: installer spec for `0.1.0`.
- `midori-v0.2.0.iss`: installer spec for `0.2.0`.
- `midori-v0.2.1.iss`: installer spec for `0.2.1`.
- `midori-v0.2.2.iss`: installer spec for `0.2.2`.
- `midori.iss`: compatibility wrapper that includes `midori-v0.1.0.iss`.

## Output

- `output/v0.1.0/`: generated `0.1.0` installer artifacts.
- `output/v0.2.0/`: generated `0.2.0` installer artifacts.
- `output/v0.2.1/`: generated `0.2.1` installer artifacts.
- `output/v0.2.2/`: generated `0.2.2` installer artifacts.
