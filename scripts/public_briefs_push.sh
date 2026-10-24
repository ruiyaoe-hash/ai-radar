#!/usr/bin/env bash
# Publish public/briefs.json on a rolling branch and one pull request.
# Never pushes to main. The pool token must not be used here. The token is not printed.
# POOL_DIR (optional): if main's briefs.json moved after this run derived, re-derive
# onto that tip instead of dropping a newer public file.
# Writes pushed, pr_url, and pr_number to $GITHUB_OUTPUT.
# pushed=true means a pull request was opened or updated, not that main moved.
set -euo pipefail

BRANCH="${BRIEFS_BRANCH:-chore/auto-briefs}"
BASE="${BRIEFS_BASE:-main}"
PR_TITLE="${BRIEFS_PR_TITLE:-快讯：自动档 / auto briefs}"
LANE_FILES=(
  public/briefs.json
  public/practice.json
  public/data/atlas.source.json
  public/data/kb.json
  public/data/topics.json
  public/data/sources.json
  public/data/creators.json
  public/data/watch.json
  public/data/topic-suggestions.json
  public/picks.json
  public/tools-radar.json
)
LANE_DIRS=(
  public/practice/inbox
  public/topics
)

emit() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    {
      echo "pushed=$1"
      echo "pr_url=${2:-}"
      echo "pr_number=${3:-}"
    } >> "$GITHUB_OUTPUT"
  fi
}

refuse_protected_branch() {
  case "$1" in
    main|master|refs/heads/main|refs/heads/master)
      echo "FAIL: refusing to publish briefs onto ${1}" >&2
      exit 1
      ;;
  esac
}

valid_ref_name() {
  case "$1" in
    *..*|*"@{"*|*[.]) return 1 ;;
  esac
  printf '%s' "$1" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._/-]*[A-Za-z0-9]$' || return 1
  git check-ref-format "refs/heads/$1"
}

check() {
  local root="$1"
  if ! env -u POOL_DIR -u AI_RADAR_POOL python3 "$root/scripts/validate.py" > /tmp/briefs-validate.log 2>&1; then
    grep -m 5 "FAIL" /tmp/briefs-validate.log >&2 || true
    tail -n 40 /tmp/briefs-validate.log >&2
    echo "FAIL: validate.py rejected the derived briefs; nothing pushed" >&2
    exit 1
  fi
}

ls_remote() {
  local try=0 out
  while [ "$try" -lt 5 ]; do
    try=$((try + 1))
    if out=$(git "${auth[@]}" ls-remote "$remote" "$1"); then
      printf '%s\n' "$out" | awk 'NR==1 {print $1}'
      return 0
    fi
    echo "briefs ls-remote attempt ${try} failed; retry" >&2
    sleep $((2 ** try))
  done
  return 1
}

fetch_base() {
  local try=0
  while [ "$try" -lt 5 ]; do
    try=$((try + 1))
    if git "${auth[@]}" fetch -q "$remote" "+refs/heads/${BASE}:refs/briefs/base"; then
      return 0
    fi
    echo "briefs fetch attempt ${try} failed; retry" >&2
    sleep $((2 ** try))
  done
  return 1
}

open_pr() {
  local json line try=0
  local owner=${GITHUB_REPOSITORY%%/*}
  while [ "$try" -lt 5 ]; do
    try=$((try + 1))
    if json=$(gh pr list --repo "$GITHUB_REPOSITORY" --base "$BASE" --head "${owner}:${BRANCH}" --state open --json number,url); then
      if ! line=$(printf '%s' "$json" | python3 -c 'import json,sys
data=json.load(sys.stdin)
if not data:
    raise SystemExit(0)
row=data[0]
print("%s %s" % (row["number"], row["url"]))'); then
        echo "FAIL: could not parse pull request list" >&2
        return 1
      fi
      printf '%s\n' "$line"
      return 0
    fi
    echo "briefs PR list attempt ${try} failed; retry" >&2
    sleep $((2 ** try))
  done
  return 1
}

ensure_pr() {
  local line number url err
  line=$(open_pr) || return 1
  if [ -n "$line" ]; then
    number=${line%% *}
    url=${line#* }
    if gh pr edit "$number" --repo "$GITHUB_REPOSITORY" --title "$PR_TITLE" --body-file "$body_file" >/dev/null; then
      PR_NUMBER=$number
      PR_URL=$url
      echo "OK briefs PR updated ${url}"
      return 0
    fi
    return 1
  fi
  err=$(mktemp)
  if url=$(gh pr create --repo "$GITHUB_REPOSITORY" --base "$BASE" --head "$BRANCH" --title "$PR_TITLE" --body-file "$body_file" 2>"$err"); then
    url=${url//$'\r'/}
    url=${url//$'\n'/}
    PR_URL=$url
    PR_NUMBER=${url##*/}
    rm -f "$err"
    case "$PR_NUMBER" in
      ''|*[!0-9]*)
        line=$(open_pr) || return 1
        PR_NUMBER=${line%% *}
        PR_URL=${line#* }
        ;;
    esac
    echo "OK briefs PR opened ${PR_URL}"
    return 0
  fi
  cat "$err" >&2 || true
  rm -f "$err"
  return 1
}

push_branch() {
  local sha="$1" try=0 expected dest
  dest="refs/heads/${BRANCH}"
  refuse_protected_branch "$BRANCH"
  case "$dest" in
    refs/heads/main|refs/heads/master)
      echo "FAIL: refusing to publish briefs onto ${dest}" >&2
      exit 1
      ;;
  esac
  while [ "$try" -lt 5 ]; do
    try=$((try + 1))
    if ! expected=$(ls_remote "$dest"); then
      echo "briefs branch push attempt ${try} failed; retry" >&2
      sleep $((2 ** try))
      continue
    fi
    if [ -n "$expected" ]; then
      if git "${auth[@]}" push -q --force-with-lease="${dest}:${expected}" "$remote" "${sha}:${dest}"; then
        return 0
      fi
    elif git "${auth[@]}" push -q "$remote" "${sha}:${dest}"; then
      return 0
    fi
    echo "briefs branch push attempt ${try} failed; retry" >&2
    sleep $((2 ** try))
  done
  return 1
}

rolling_matches() {
  local base_sha="$1" parent current
  if ! git "${auth[@]}" fetch -q "$remote" "+refs/heads/${BRANCH}:refs/briefs/rolling"; then
    return 1
  fi
  parent=$(git rev-parse --verify 'refs/briefs/rolling^' 2>/dev/null || true)
  [ "$parent" = "$base_sha" ] || return 1
  git -C "$work" diff --quiet "refs/briefs/rolling" -- "${LANE_FILES[@]}" "${LANE_DIRS[@]}"
}

write_pr_body() {
  body_file=$(mktemp)
  cat > "$body_file" <<'EOF'
自动档快讯，以及写清了的做法、领域进展和由它们派生的公开页。

分支 `chore/auto-briefs` 从最新 `main` 重建。`validate-and-derive` 变绿后再合并。合并进 `main` 之后，`deploy-pages.yml` 才会部署 Pages。不推 `main`。

用 `GITHUB_TOKEN` 打开的 PR，检查可能先停在 Approve workflows。点批准，等它变绿，再合并。这不是分支保护失效。不要直推 `main`，也不要给 Actions 开 bypass。

Auto-band briefs plus finished practice, watch, and derived public pages. Rolling branch `chore/auto-briefs`, rebuilt from the current `main` tip. Merge after `validate-and-derive` is green. Pages deploys on that merge. This script does not push main.
EOF
}

finish_pr() {
  local try=0
  write_pr_body
  while [ "$try" -lt 5 ]; do
    try=$((try + 1))
    if ensure_pr; then
      return 0
    fi
    echo "briefs PR attempt ${try} failed; retry" >&2
    sleep $((2 ** try))
  done
  echo "FAIL: could not open or update the briefs pull request" >&2
  return 1
}

work=""
derived=""
body_file=""
cleanup() {
  if [ -n "$work" ]; then
    git worktree remove --force "$work" >/dev/null 2>&1 || rm -rf "$work"
  fi
  git worktree prune >/dev/null 2>&1 || true
  git update-ref -d refs/briefs/base >/dev/null 2>&1 || true
  git update-ref -d refs/briefs/rolling >/dev/null 2>&1 || true
  rm -f "$body_file"
}
trap cleanup EXIT

if [ -z "${GITHUB_TOKEN:-}" ] || [ -z "${GITHUB_REPOSITORY:-}" ]; then
  echo "无 GITHUB_TOKEN，跳过公开快讯推送"
  emit false
  exit 0
fi

export GH_TOKEN="$GITHUB_TOKEN"
export GIT_TERMINAL_PROMPT=0

if ! valid_ref_name "$BRANCH" || ! valid_ref_name "$BASE"; then
  echo "FAIL: bad briefs branch name" >&2
  exit 1
fi
if [ "$BRANCH" = "$BASE" ]; then
  echo "FAIL: refusing to publish briefs onto ${BRANCH}" >&2
  exit 1
fi
refuse_protected_branch "$BRANCH"

if [ -z "$(git status --porcelain -- "${LANE_FILES[@]}" "${LANE_DIRS[@]}")" ]; then
  echo "公开页无更新"
  emit false
  exit 0
fi

basic=$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 -w 0)
echo "::add-mask::${basic}"
remote="${PUBLIC_REMOTE:-https://github.com/${GITHUB_REPOSITORY}.git}"
auth=(-c "http.extraheader=AUTHORIZATION: basic ${basic}")

if ! fetch_base; then
  echo "FAIL: could not fetch ${BASE}" >&2
  exit 1
fi
base_sha=$(git rev-parse refs/briefs/base)
head_sha=$(git rev-parse HEAD)

work=$(mktemp -d)
rmdir "$work"
git worktree add -q --detach "$work" "$base_sha"

copy_lanes() {
  local dest="$1" rel
  for rel in "${LANE_FILES[@]}"; do
    if [ -f "$rel" ]; then
      mkdir -p "$dest/$(dirname "$rel")"
      cp -a "$rel" "$dest/$rel"
    fi
  done
  for rel in "${LANE_DIRS[@]}"; do
    if [ -d "$rel" ]; then
      rm -rf "$dest/$rel"
      mkdir -p "$dest/$(dirname "$rel")"
      cp -a "$rel" "$dest/$rel"
    fi
  done
}

if ! git diff --quiet "$head_sha" "$base_sha" -- "${LANE_FILES[@]}" "${LANE_DIRS[@]}"; then
  if [ -z "${POOL_DIR:-}" ] || [ ! -d "$POOL_DIR" ]; then
    echo "FAIL: public lanes on ${BASE} moved since derive; POOL_DIR is unset" >&2
    exit 1
  fi
  pool_abs=$(cd "$POOL_DIR" && pwd)
  if ! (
    cd "$work"
    python3 scripts/project_public_lanes.py --pool-dir "$pool_abs"
    python3 scripts/derive_briefs.py --pool-dir "$pool_abs" --briefs public/briefs.json
    python3 scripts/generate_derived.py
  ); then
    echo "FAIL: re-derive on ${BASE} failed; nothing pushed" >&2
    exit 1
  fi
else
  copy_lanes "$work"
fi

if [ -z "$(git -C "$work" status --porcelain -- "${LANE_FILES[@]}" "${LANE_DIRS[@]}")" ]; then
  echo "公开页与 ${BASE} 一致"
  emit false
  exit 0
fi

remote_tip=$(ls_remote "refs/heads/${BRANCH}") || {
  echo "FAIL: could not read ${BRANCH}" >&2
  exit 1
}
if [ -n "$remote_tip" ] && rolling_matches "$base_sha"; then
  existing=$(open_pr) || exit 1
  if [ -n "$existing" ]; then
    echo "滚动分支已是当前 main 上的这份快讯"
    emit false "${existing#* }" "${existing%% *}"
    exit 0
  fi
  echo "滚动分支已有这份快讯，补开 PR"
  finish_pr
  emit true "$PR_URL" "$PR_NUMBER"
  exit 0
fi

check "$work"
git -C "$work" add -- "${LANE_FILES[@]}" "${LANE_DIRS[@]}"
if git -C "$work" diff --cached --quiet; then
  echo "公开页无更新"
  emit false
  exit 0
fi
git -C "$work" \
  -c user.name="github-actions[bot]" \
  -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
  commit -q -m "public: briefs and finished visitor lanes"
sha=$(git -C "$work" rev-parse HEAD)

if ! push_branch "$sha"; then
  echo "FAIL: briefs branch push failed after retries" >&2
  exit 1
fi
echo "OK briefs branch ${BRANCH}"
finish_pr
emit true "$PR_URL" "$PR_NUMBER"
