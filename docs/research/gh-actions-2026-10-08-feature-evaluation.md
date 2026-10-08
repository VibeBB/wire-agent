# GitHub Actions 2026-10-08 feature evaluation

Reviewed on 2026-10-08 against the upstream release notes for the three
action bumps applied in this change. New tags were resolved with
`git ls-remote`; all three are lightweight tags and the `uses:` pins now
carry the tag commit SHAs.

## step-security/harden-runner v2.21.1 -> v2.22.0

| Change | Decision | Wire assessment |
| --- | --- | --- |
| Linux ARM64 support for community tier | n/a | All workflows run `ubuntu-26.04` x64 GitHub-hosted runners; nothing to adopt. |
| GHES support for self-hosted VMs (enterprise tier) | n/a | This repo runs on github.com, not GHES; enterprise tier is not in use. |
| macOS/Windows runner deny list for block policy (enterprise tier) | n/a | No macOS/Windows jobs and no enterprise tier; the block policy is unchanged. |

## actions/upload-artifact v7.0.1 -> v7.0.2

| Change | Decision | Wire assessment |
| --- | --- | --- |
| `@actions/artifact` v6.3.1: retries on HTTP 429 honoring Retry-After | inherent | Reliability fix only — no input, output, or behavior-contract change; the SARIF/report uploads in `ci.yml`, `scorecard.yml`, `container-audit.yml`, `mutation.yml`, `locked-image-check.yml`, and `publish-wire-images.yml` benefit automatically. |

## actions/download-artifact v8.0.1 -> v8.0.2

| Change | Decision | Wire assessment |
| --- | --- | --- |
| `@actions/artifact` v6.3.1: retries on HTTP 429 honoring Retry-After | inherent | Same reliability fix on the download side; the `scorecard.yml` artifact fetch is the only consumer and benefits automatically. |
| README update | n/a | Documentation only; no workflow impact. |

No release changes the `uses:` interface (inputs, outputs, or step
contract), so the pins were updated in place — including inside the
hash-locked shared workflows, whose `EXPECTED` entries in
`scripts/check_shared_workflows.py` were refreshed in the same change.
