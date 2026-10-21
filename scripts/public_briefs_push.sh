#!/usr/bin/env bash
# Commit public/briefs.json only, validate, rebase, and push with the workflow token.
# The pool token must not be used here. The token is not printed.
# POOL_DIR (optional): on a rebase conflict, reset to the remote and re-derive
# from the pool instead of overwriting someone else's briefs.json.
# Writes pushed=true|false to $GITHUB_OUTPUT so the caller can trigger a deploy.
set -euo pipefail

emit() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "pushed=$1" >> "$GITHUB_OUTPUT"
  fi
}

if [ -z "${GITHUB_TOKEN:-}" ] || [ -z "${GITHUB_REPOSITORY:-}" ]; then
  echo "无 GITHUB_TOKEN，跳过公开快讯推送"
  emit false
  exit 0
fi

# Public-output checks only. Archive ↔ pool traceability is a separate concern and
# must not hold back a brief, so the pool path is hidden from validate.py here.
check() {
  if ! env -u POOL_DIR -u AI_RADAR_POOL python3 scripts/validate.py > /tmp/briefs-validate.log 2>&1; then
    grep -m 5 "FAIL" /tmp/briefs-validate.log >&2 || true
    tail -n 40 /tmp/briefs-validate.log >&2
    echo "FAIL: validate.py rejected the derived briefs; nothing pushed" >&2
    exit 1
  fi
}

commit_briefs() {
  git add -- public/briefs.json
  if git diff --cached --quiet; then
    return 1
  fi
  git -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit -q -m "briefs: auto band from scored pool"
}

if git diff --quiet HEAD -- public/briefs.json; then
  echo "快讯无更新"
  emit false
  exit 0
fi
check
commit_briefs

branch=$(git rev-parse --abbrev-ref HEAD)
basic=$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 -w 0)
echo "::add-mask::${basic}"
remote="${PUBLIC_REMOTE:-https://github.com/${GITHUB_REPOSITORY}.git}"
auth=(-c "http.extraheader=AUTHORIZATION: basic ${basic}")

try=0
while [ "$try" -lt 5 ]; do
  try=$((try + 1))
  if ! git "${auth[@]}" fetch -q "$remote" "$branch"; then
    echo "briefs fetch attempt ${try} failed; retry" >&2
    sleep $((2 ** try))
    continue
  fi
  if ! git rebase -q FETCH_HEAD; then
    git rebase --abort >/dev/null 2>&1 || true
    if [ -z "${POOL_DIR:-}" ]; then
      echo "FAIL: public/briefs.json conflicts with the remote and POOL_DIR is unset" >&2
      exit 1
    fi
    echo "briefs.json 与远端冲突：以远端为底重新派生" >&2
    git reset -q --hard FETCH_HEAD
    python3 scripts/derive_briefs.py --pool-dir "$POOL_DIR" --briefs public/briefs.json
    if git diff --quiet HEAD -- public/briefs.json; then
      echo "重新派生后无差异"
      emit false
      exit 0
    fi
    check
    commit_briefs
  fi
  if git "${auth[@]}" push -q "$remote" "HEAD:${branch}"; then
    echo "OK briefs push"
    emit true
    exit 0
  fi
  echo "briefs push attempt ${try} failed; retry" >&2
  sleep $((2 ** try))
done
echo "FAIL: briefs push failed after retries" >&2
exit 1
