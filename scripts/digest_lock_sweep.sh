#!/usr/bin/env bash
# Digest lock PR sweep — retries merges of stalled bot digest-lock PRs and
# dispatches post-merge verification on main (bot merges do not fire push
# events). Driven by .github/workflows/digest-lock-sweep.yml; exits nonzero
# when a required dispatch fails instead of swallowing it.
set -uo pipefail
# GH_TOKEN must carry actions:write + pull-requests:write + contents:write
# on $GITHUB_REPOSITORY.

repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
summary_file="${GITHUB_STEP_SUMMARY:-/dev/null}"
post_merge_workflows="${SWEEP_POST_MERGE_WORKFLOWS:-ci.yml locked-image-check.yml}"
merged_cutoff="${SWEEP_MERGED_CUTOFF:-7 hours ago}"
digest_prefix="bot/update-image-digests-"
dispatch_post_merge=false
failures=0

# Lock PRs sometimes stay open with auto-merge armed and every required
# check green while GitHub's mergeability evaluation reports "blocked"
# indefinitely. Re-try the merge every 6 hours; the branch ruleset still
# gates it, so an unsatisfied PR cannot merge.
prs=$(gh pr list --repo "$repo" --state open --limit 50 \
  --json number,headRefName \
  --jq ".[] | select(.headRefName | startswith(\"$digest_prefix\")) | .number")
if [ -z "$prs" ]; then
  echo "no open digest-lock PRs" | tee -a "$summary_file"
else
  for pr in $prs; do
    pr_url="https://github.com/$repo/pull/$pr"
    state=$(gh api "repos/$repo/pulls/$pr" \
      --jq '.mergeable_state // "unknown"' || echo unknown)
    case "$state" in
      clean|blocked|behind|unstable)
        if gh pr merge --repo "$repo" --squash --delete-branch "$pr"; then
          echo "merged $pr_url (was $state)" | tee -a "$summary_file"
          dispatch_post_merge=true
        else
          gh pr merge --repo "$repo" --auto --squash --delete-branch "$pr" || true
          echo "$pr_url left open ($state; auto-merge armed)" | tee -a "$summary_file"
        fi
        ;;
      *)
        echo "$pr_url skipped (mergeable_state=$state)" | tee -a "$summary_file"
        ;;
    esac
  done
fi

# Bot merges do not fire push events, so a lock merge that landed outside a
# live publisher — a merge above, or an auto-merge armed by the publisher
# that completed after it exited — never triggers the post-merge workflows.
# Cover any recent lock merge that has no ci.yml dispatch since its merge;
# one run verifies main.
if [ "$dispatch_post_merge" != true ]; then
  cutoff=$(date -u -d "$merged_cutoff" +%Y-%m-%dT%H:%M:%SZ)
  while IFS= read -r merged_at; do
    [ -n "$merged_at" ] || continue
    [ "$merged_at" \> "$cutoff" ] || continue
    runs=$(gh run list --repo "$repo" --workflow ci.yml \
      --branch main --event workflow_dispatch \
      --created ">=$merged_at" --json databaseId --jq 'length' || echo 0)
    if [ "${runs:-0}" = "0" ]; then
      dispatch_post_merge=true
      break
    fi
  done < <(gh pr list --repo "$repo" --state merged --limit 10 \
    --json headRefName,mergedAt \
    --jq ".[] | select(.headRefName | startswith(\"$digest_prefix\")) | .mergedAt")
fi

if [ "$dispatch_post_merge" = true ]; then
  for workflow in $post_merge_workflows; do
    if gh workflow run "$workflow" --repo "$repo" --ref main; then
      echo "dispatched $workflow on main" | tee -a "$summary_file"
    else
      echo "::error::failed to dispatch $workflow on main" | tee -a "$summary_file" >&2
      failures=$((failures + 1))
    fi
  done
fi
exit "$failures"
