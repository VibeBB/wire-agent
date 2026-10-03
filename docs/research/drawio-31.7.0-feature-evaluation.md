# drawio-desktop 31.5.3 -> 31.7.0 feature evaluation

Reviewed on 2026-10-03 against the v31.7.0 release notes and the draw.io
core changelog for the 31.5.3 -> 31.7.0 range (the desktop release carries
every core change in that window; there were no intermediate 31.6.x desktop
releases). `releases/latest` resolves to `v31.7.0`, and the
`drawio-amd64-31.7.0.deb` asset was downloaded and its SHA-256 computed as
`eb9695e208fcc5ccfbfc496aa8ab2f52a273297d83715de2177b231c172c13de`; the
Dockerfile pin uses that value.

| Change | Decision | Wire assessment |
| --- | --- | --- |
| Electron 44.5.1 | inherent | Runtime bump of the packaged app; the export uses the unmodified binary as a subprocess, so there is nothing to adopt. |
| Blank-page loads no longer replace the editor window | n/a | The export runs `drawio -x` headless under `xvfb-run`; no editor window exists. |
| Offline keyboard-shortcuts dialog | n/a | GUI-only feature; the CLI export never opens the UI. |
| Transparent PNG export fixed for diagrams with a background colour | inherent | Improves correctness of `--transparent` exports; the export helper does not pass that flag, and transparent output now simply behaves correctly if a caller requests it. |
| PDF export embeds math source as text; PNG math output pixel-identical to 31.5.3 | inherent | The harness diagram path does not emit math formulas; exports remain byte-comparable. |
| Page animations export as animated GIF / H.264 MP4 | not adopted | The export contract emits PNG/SVG/PDF wire-harness diagrams; video/GIF targets are out of scope. |
| Undo/redo while the colour picker has focus; connector click-connects two selected shapes | n/a | Editor interactions; not reachable through `drawio -x`. |
| Math rendering loads on first use | inherent | Lazy loading only affects the GUI startup path. |
| Security fuses (RunAsNode/NODE_OPTIONS/inspect disabled) | inherent | Hardening of the packaged binary; the image keeps invoking it unchanged. |

No new feature changes the harness diagram/export contract. `--timeout` and
`--normalize` continue to be probed dynamically by `src/wire/export.py`, so
the CLI surface needs no change.
