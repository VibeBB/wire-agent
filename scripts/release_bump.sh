#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=${RELEASE_BUMP_REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}
cd "$REPO_ROOT"

version_args=(--bump "$BUMP")
if [[ -n "$SET_VERSION" ]]; then
  version_args=(--set "${SET_VERSION#v}")
fi
version=$(python3 "$SCRIPT_DIR/bump_version.py" --root "$REPO_ROOT" --dry-run "${version_args[@]}")

status=0
git ls-remote --exit-code --tags origin "refs/tags/v$version" >/dev/null || status=$?
case "$status" in
  0) echo "::error::tag v$version already exists" >&2; exit 1 ;;
  2) ;;
  *) echo "::error::could not check whether tag v$version exists" >&2; exit "$status" ;;
esac

if [[ "$DRY_RUN" == true ]]; then
  echo "dry-run: would open a version bump PR for v$version" >> "$GITHUB_STEP_SUMMARY"
  exit 0
fi

branch="bot/release-bump-v$version-$GITHUB_RUN_ID"
existing=$(gh pr list --repo "$GITHUB_REPOSITORY" --base main --head "$branch" \
  --state all --json url --jq '.[0].url // empty')
if [[ -n "$existing" ]]; then
  echo "version-bump PR: $existing" >> "$GITHUB_STEP_SUMMARY"
  exit 0
fi

python3 "$SCRIPT_DIR/bump_version.py" --root "$REPO_ROOT" "${version_args[@]}" >/dev/null
git add -- pyproject.toml uv.lock plugins/wire/.plugin/plugin.json plugins/wire/skills/*/SKILL.md
status=0
git ls-remote --exit-code --heads origin "refs/heads/$branch" >/dev/null || status=$?
case "$status" in
  0)
    git fetch --no-tags origin "refs/heads/$branch"
    [[ "$(git rev-parse 'FETCH_HEAD^{tree}')" == "$(git write-tree)" ]] ||
      { echo "::error::existing bump branch does not match this run's version files" >&2; exit 1; }
    ;;
  2)
    git -c user.name='github-actions[bot]' \
      -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
      commit -m "Release v$version: update version files"
    git push origin "HEAD:refs/heads/$branch"
    ;;
  *) exit "$status" ;;
esac
pr_url=$(gh pr create --repo "$GITHUB_REPOSITORY" --base main --head "$branch" \
  --title "Release v$version: update version files" \
  --body "Merge after the required checks, then create and push v$version from the verified main commit.")
echo "version-bump PR: $pr_url" >> "$GITHUB_STEP_SUMMARY"
