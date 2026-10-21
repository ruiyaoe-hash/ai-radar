#!/usr/bin/env bash
# Rebase onto the remote pool branch, then push. Retry when RSS and X ingest
# both write candidates/. Run from the private pool checkout.
# Never prints remotes or tokens. COMMIT_MESSAGE is required.
# POOL_TOKEN (optional) is sent as an http header for this script only, so the
# checkout can run with persist-credentials: false and earlier steps never see it.
# The workflows share concurrency group pool-writer, so a rebase conflict means a
# human edited the same file: stop instead of overwriting it.
set -euo pipefail

auth=()
if [ -n "${POOL_TOKEN:-}" ]; then
  basic=$(printf 'x-access-token:%s' "$POOL_TOKEN" | base64 -w 0)
  echo "::add-mask::${basic}"
  auth=(-c "http.extraheader=AUTHORIZATION: basic ${basic}")
fi

if [ -z "${COMMIT_MESSAGE:-}" ]; then
  echo "FAIL: COMMIT_MESSAGE is empty" >&2
  exit 1
fi
if [ "$#" -eq 0 ]; then
  echo "FAIL: pass paths to commit, for example candidates review" >&2
  exit 1
fi

paths=()
for path in "$@"; do
  if [ -e "$path" ]; then
    paths+=("$path")
  fi
done
if [ "${#paths[@]}" -eq 0 ]; then
  echo "无更新"
  exit 0
fi
git add -- "${paths[@]}"
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
  if ! git "${auth[@]}" fetch -q origin "$branch"; then
    echo "pool fetch attempt ${try} failed; retry" >&2
    sleep $((2 ** try))
    continue
  fi
  if ! git rebase -q FETCH_HEAD; then
    git rebase --abort >/dev/null 2>&1 || true
    echo "FAIL: pool rebase conflict; someone edited the same candidates/ or review/ file. Resolve by hand." >&2
    exit 1
  fi
  if git "${auth[@]}" push -q origin "HEAD:${branch}"; then
    echo "OK pool push"
    exit 0
  fi
  echo "pool push attempt ${try} failed; retry" >&2
  sleep $((2 ** try))
done
echo "FAIL: pool push failed after retries" >&2
exit 1
