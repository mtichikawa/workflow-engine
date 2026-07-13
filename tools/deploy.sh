#!/usr/bin/env bash
#
# Regenerate the use-case explorers + gallery and copy them into the live site repo
# (github.com/mtichikawa/workflow-engine → mtichikawa.github.io/workflow-engine/usecases/).
#
# The two repos are NOT auto-synced: this repo is the source of truth, the site repo holds a
# copied snapshot. Run this after changing recipes / run logs / the explorer/gallery generators.
#
#   tools/deploy.sh                       # rebuild + copy into ~/code/workflow-engine
#   tools/deploy.sh /path/to/site-repo    # rebuild + copy into a different checkout
#   tools/deploy.sh --push                # also commit + push the site repo (asks nothing — be sure)
#
# The writeup page (workflow-engine/index.html) is hand-maintained and is never touched here.

set -euo pipefail
cd "$(dirname "$0")/.."                      # engine repo root

PUSH=0
DEST="$HOME/code/workflow-engine"
for arg in "$@"; do
  case "$arg" in
    --push) PUSH=1 ;;
    *) DEST="$arg" ;;
  esac
done
SITE="$DEST/usecases"

if [ ! -d "$DEST/.git" ]; then
  echo "✗ site repo not found at: $DEST" >&2
  echo "  pass the path explicitly:  tools/deploy.sh /path/to/workflow-engine" >&2
  exit 1
fi

echo "→ regenerating explorers + gallery"
python3 tools/build_explorer.py            # triage / content / refine  → usecases/<slug>/index.html
python3 tools/build_gallery.py             # gallery                    → usecases/index.html

echo "→ copying static files into $SITE"
mkdir -p "$SITE/triage" "$SITE/content" "$SITE/refine"
cp usecases/index.html "$SITE/index.html"
for s in triage content refine; do
  cp "usecases/$s/index.html" "$SITE/$s/index.html"
done

echo "→ site repo status:"
git -C "$DEST" status --short usecases || true

if [ "$PUSH" -eq 1 ]; then
  echo "→ committing + pushing the site repo"
  git -C "$DEST" add usecases
  git -C "$DEST" commit -q -m "Redeploy use-case gallery + explorers from engine" || echo "  (nothing to commit)"
  git -C "$DEST" push
  echo "✓ deployed and pushed — live shortly at https://mtichikawa.github.io/workflow-engine/usecases/"
else
  echo "✓ files copied. Review, then:  git -C \"$DEST\" add usecases && git -C \"$DEST\" commit && git -C \"$DEST\" push"
  echo "  (or re-run with --push to do that automatically)"
fi
