#!/usr/bin/env bash
# Rebase onto the remote pool branch, then push. Retry when RSS and X ingest
# both write candidates/. Run from the private pool checkout.
# Never prints remotes or tokens. COMMIT_MESSAGE is required.
set -euo pipefail

if [ -z "${COMMIT_MESSAGE:-}" ]; then
  echo "FAIL: COMMIT_MESSAGE is empty" >&2
  exit 1
fi
if [ "$#" -eq 0 ]; then
  echo "FAIL: pass paths to commit, for example candidates review" >&2
  exit 1
fi

git add -- "$@"
if git diff --cached --quiet; then
  echo "无更新"
  exit 0
fi
git -c user.name="github-actions[bot]" \
  -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
  commit -m "$COMMIT_MESSAGE"

branch=$(git rev-parse --abbrev-ref HEAD)
try=0
while [ "$try" -lt 5 ]; do
  try=$((try + 1))
  if git pull --rebase origin "$branch" && git push origin HEAD; then
    echo "OK pool push"
    exit 0
  fi
  git rebase --abort >/dev/null 2>&1 || true
  echo "pool push attempt ${try} failed; retry" >&2
  sleep $((2 ** try))
done
echo "FAIL: pool push failed after retries" >&2
exit 1
