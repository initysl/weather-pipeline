#!/usr/bin/env bash
# Publish the exported CSVs as the only contents of the `data` branch.
#
#   scripts/publish_data_branch.sh <exports-dir> <git-remote-url>
#
# The branch is replaced on every run (force-push of a single commit): charts only
# need the latest files, and the full history already lives in the database.
set -euo pipefail

src_dir=$1
remote=$2
branch=${DATA_BRANCH:-data}

shopt -s nullglob
files=("$src_dir"/*.csv)
if [ ${#files[@]} -eq 0 ]; then
    echo "No CSV files in $src_dir; nothing published" >&2
    exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "${files[@]}" "$work"/

as_of=$(date -u +%F)
{
    echo "# Chart data"
    echo
    echo "Published automatically by the *Daily weather load* workflow. Last updated: $as_of (UTC)."
    echo "Do not edit: this branch is replaced on every run."
    echo
    for f in "${files[@]}"; do echo "- \`$(basename "$f")\`"; done
} > "$work/README.md"

cd "$work"
git init -q -b "$branch"
git add -A
git -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit -q -m "Chart data as of $as_of"
git push -q --force "$remote" "HEAD:$branch"
echo "Published ${#files[@]} files to branch '$branch'"
