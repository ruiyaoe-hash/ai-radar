#!/usr/bin/env bash
# Commit public/briefs.json only, rebase, and push with the workflow token.
# The pool token must not be used here. The token is not printed.
set -euo pipefail

if [ -z "${GITHUB_TOKEN:-}" ] || [ -z "${GITHUB_REPOSITORY:-}" ]; then
  echo "无 GITHUB_TOKEN，跳过公开快讯推送"
  exit 0
fi

git add -- public/briefs.json
if git diff --cached --quiet; then
  echo "快讯无更新"
  exit 0
fi

git -c user.name="github-actions[bot]" \
  -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
  commit -m "briefs: auto band from scored pool"

branch=$(git rev-parse --abbrev-ref HEAD)
basic=$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 -w 0)
try=0
while [ "$try" -lt 5 ]; do
  try=$((try + 1))
  if git pull --rebase origin "$branch" \
    && git -c "http.extraheader=AUTHORIZATION: basic ${basic}" \
      push "https://github.com/${GITHUB_REPOSITORY}.git" "HEAD:${branch}"; then
    echo "OK briefs push"
    exit 0
  fi
  git rebase --abort >/dev/null 2>&1 || true
  echo "briefs push attempt ${try} failed; retry" >&2
  sleep $((2 ** try))
done
echo "FAIL: briefs push failed after retries" >&2
exit 1
