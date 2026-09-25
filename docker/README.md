# wire Docker images

## Purpose

`wire-tools.Dockerfile` bundles the deterministic `wire` core (contract
schema, gates, exporters) into a single execution environment published to
GHCR as `ghcr.io/vibebb/wire-tools`.

Docker does not guarantee determinism. Time, locale, filesystem, and CPU
differences remain, so manifest hashes and the gate rules stay required —
the image pins the toolchain, not the outputs.

## Contents

| Content | Pin |
| --- | --- |
| Debian | `13` slim (`debian:13-slim`) |
| uv | `0.12.18` (`ghcr.io/astral-sh/uv:0.12.18`, also `ARG UV_VERSION`) |
| Python | `3.12` via `uv python install` (matches `requires-python` and the CI matrix floor) |
| wire + runtime deps | `uv export --frozen --no-dev` from `uv.lock` |

The package is installed into `/opt/wire/.venv` (first on `PATH`). Source
tree, plugin, `e2e_authoring.py`, and `examples/` are copied to `/opt/wire`.
Runtime user is `wire` (uid 1000).

## Build

```bash
docker build \
  --file docker/wire-tools.Dockerfile \
  --build-arg IMAGE_REVISION="$(git rev-parse HEAD)" \
  --tag wire-tools:local \
  .
```

## Run

```bash
docker run --rm wire-tools:local python -m wire doctor
docker run --rm wire-tools:local \
  python /opt/wire/scripts/e2e_authoring.py \
    --contract /opt/wire/examples/sensor-harness/sensor-harness.contract.json \
    --out /tmp/out
```

## Image digests

`docker/image-digests.json` is written only by the publish workflow; no
placeholder entries are committed while no published digest exists.
