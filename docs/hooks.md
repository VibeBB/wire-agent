# Hooks

Plugin hooks are declared in `plugins/wire/hooks/hooks.json`; task
sub-agents redeclare the ones they need in their frontmatter
([agents.md](agents.md)). Every hook resolves the plugin root from
`$WIRE_PLUGIN_ROOT`, `${OPENHANDS_PROJECT_DIR}/plugins/wire`,
`~/.agents/plugins/wire` or `~/.openhands/plugins/installed/wire` and runs
a stdlib-only script from `hooks/scripts/` on the host.

| Event | Matcher | Hook | Script | Effect |
| --- | --- | --- | --- | --- |
| `session_start` | `*` | `wire-doctor` | `wire_launcher.py doctor --warn` | Probes docker/image/drawio; warns, never blocks. |
| `session_start` | `*` | `intake-attachments` | `intake_attachments.py` | Materializes attached images to `intake/attachments/<sha256[:12]>.<ext>` + `manifest.jsonl`. |
| `session_start` | `*` | `ensure-llm-profiles` | `ensure_llm_profiles.py` | Creates `vibebb-author`/`vibebb-review` profiles from the active profile when missing (shared canon). |
| `session_start` | `*` | `require-records` | `require_records.py session-start` | Writes the session marker for VRP enforcement (shared canon). |
| `user_prompt_submit` | `*` | `intake-attachments` | `intake_attachments.py` | Same as above for each new prompt. |
| `pre_tool_use` | `file_editor\|apply_patch\|terminal` | `protect-generated` | `protect_generated.py` | Denies edits to projections, record logs and liaison responses. |
| `pre_tool_use` | `terminal` | `safety-rail` | `safety_rail.py` | Denies a fixed list of destructive commands (shared canon). |
| `post_tool_use` | `inspect_image_with_vision` | `record-vision-tool-event` | `record_vision_tool_event.py` | Logs the vision call so a vision review is owed. |
| `post_tool_use` | `file_editor\|wire_drawio\|wire_author\|wire_view_image` | `record-image-observation` | `record_image_observation.py` | Logs each image the model saw (by sha256) so a vision review is owed. |
| `stop` | `*` | `require-records` | `require_records.py stop` | Refuses to stop while decisions, impressions or vision reviews are owed (max two refusals). |
| `stop` | `*` | `report-design-status` | `report_design_status.py` | Prints design-report verdicts and lists unreviewed images. |
| `stop` | `*` | `intake-attachments` | `intake_attachments.py` | Final attachment sweep. |

`hooks/records-policy.json` lists the artifact globs whose changes need a
stage impression. `_records.py`, `require_records.py`,
`ensure_llm_profiles.py`, `safety_rail.py` and `_provenance.py` are family
canon: `scripts/check_shared_hooks.py` compares their normalized AST
hashes and fails CI on any local edit.

Hook failures never block a session except where the table says
"denies"/"refuses".
