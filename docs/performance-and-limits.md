# Performance and limits

## Runtime budgets

| Item | Limit | Where |
| --- | --- | --- |
| drawio export per file | 300 s (`--timeout`, when drawio supports it) | `src/wire/drawio_cli.py` |
| drawio subprocess | 420 s hard timeout | `src/wire/drawio_cli.py` |
| drawio `--timeout` probe | 30 s | `src/wire/drawio_cli.py` |
| `docker image inspect` | 30 s | `wire_launcher.py` |
| `docker pull` of the tools image | 900 s | `wire_launcher.py` |
| image attestation verify | 120 s (`gh auth` probe 15 s) | `wire_launcher.py` |
| `wire-brief` / `wire-design` | 40 iterations, 3.0 USD per run | agent frontmatter |
| `wire-review` | 30 iterations, 2.0 USD per run | agent frontmatter |
| Stop refusals by `require-records` | 2, then the stop is allowed with a warning | `hooks/records-policy.json` |
| `report-design-status` search depth | 4 directory levels | hook script |

The gates are pure Python over the contract: a contract with hundreds of
wires gates in well under a second. Rendering dominates `wire_author`
time (drawio-desktop under `xvfb-run`, typically a few seconds per
format).

## Sandbox

Every wire command runs in the digest-pinned `wire-tools` image with
`--network none`, `--cap-drop ALL`, `no-new-privileges`, the host uid,
the workspace bind-mounted at its own path and the plugin source mounted
read-only. Only `OPENHANDS_*`/`WIRE_*` and a few named variables are
forwarded. There is no host fallback: without docker or the image the
command fails closed.

## Modelling limits

- Routes are declared (segments with lengths and bend radii), not
  computed in 3D. `route_geometry` only checks that a route is at least
  as long as the straight-line polyline through its placed anchors; it
  does not check clearance, sag or slack.
- The route plan is a top view (x/y) of anchor positions; z is ignored
  in the drawing.
- Ampacity uses the declared reference ampacity with temperature
  derating and a bundle factor; it is not a thermal simulation.
- Voltage drop uses DC resistance at the declared value
  (default limit 3 % of the net voltage when `max_voltage_drop_v` is
  absent).
- No formboard (nail board) layout and no KBL/VEC export yet; `kbl` and
  `vec` are accepted only as provenance systems.
- Vision is advisory. If no vision-capable model or profile is
  available, vision is skipped and recorded as such; gate authority does
  not change.
- `wire_view_image` accepts PNG and JPEG only.
- Rendered raster bytes depend on the drawio and font versions in the
  image; the manifest records actual hashes and `--baseline` detects
  changes.
