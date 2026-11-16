#!/usr/bin/env bash
# Put a new frontend build live without deleting the previous build's chunks (#20): a tab opened
# before the deploy still loads its lazy pages (Aufgabe, Karten …) instead of failing. index.html
# switches last. Old chunks are small; a plain `npm run build` clears them when nobody is studying.
set -euo pipefail
cd "$(dirname "$0")/../app"
next=dist-next
rm -rf "$next"
npx vite build --outDir "$next" --emptyOutDir
mkdir -p dist/assets
cp -r "$next"/assets/. dist/assets/
find "$next" -mindepth 1 -maxdepth 1 ! -name index.html ! -name assets -exec cp -r {} dist/ \;
cp "$next"/index.html dist/index.html
rm -rf "$next"
systemctl --user restart kaskade-web
