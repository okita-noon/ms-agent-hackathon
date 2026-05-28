#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/new_agent_worktree.sh <agent> <task-slug> [base-ref]

Examples:
  scripts/new_agent_worktree.sh codex login-copy-update
  scripts/new_agent_worktree.sh claude exception-modal origin/main

Creates a dedicated git worktree from origin/main by default:
  .codex/worktrees/<task-slug>   -> branch codex/<task-slug>
  .claude/worktrees/<task-slug>  -> branch claude/<task-slug>
USAGE
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage >&2
  exit 2
fi

agent="$1"
task_slug="$2"
base_ref="${3:-origin/main}"

case "$agent" in
  codex|claude) ;;
  *)
    echo "ERROR: agent must be 'codex' or 'claude'" >&2
    exit 2
    ;;
esac

if [[ ! "$task_slug" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
  echo "ERROR: task-slug must match ^[a-z0-9][a-z0-9._-]*$" >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
branch="${agent}/${task_slug}"
worktree_path="${repo_root}/.${agent}/worktrees/${task_slug}"

if [[ -e "$worktree_path" ]]; then
  echo "ERROR: worktree path already exists: $worktree_path" >&2
  exit 1
fi

if git show-ref --verify --quiet "refs/heads/${branch}"; then
  echo "ERROR: branch already exists: $branch" >&2
  exit 1
fi

mkdir -p "$(dirname "$worktree_path")"

echo "Fetching origin main..."
git fetch origin main

echo "Creating worktree..."
git worktree add -b "$branch" "$worktree_path" "$base_ref"

cat <<EOF

Created worktree:
  path:   $worktree_path
  branch: $branch

Next:
  cd "$worktree_path"
EOF
