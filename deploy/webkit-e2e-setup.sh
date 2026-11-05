#!/usr/bin/env bash
# #28: run the Karten E2E tests in WebKit (Safari's engine) on this box — no root needed.
# Playwright has no WebKit build for Ubuntu 26.04: this fetches the 24.04 one, unpacks the libraries it
# misses into ~/.cache/wk-noble/root (24.04 packages, plus 26.04 ones where they must match the system's
# Mesa and GStreamer) and lets Playwright's MiniBrowser wrapper keep LD_LIBRARY_PATH. Safe to re-run.
#
# Then:  cd app && PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 \
#          KASKADE_WEBKIT_ROOT=$HOME/.cache/wk-noble/root KASKADE_DIST=<scratch build> \
#          npx playwright test -c playwright.kaskade.config.js --project webkit
set -euo pipefail

S="$HOME/.cache/wk-noble"
ROOT="$S/root"
APP="$(cd "$(dirname "$0")/../app" && pwd)"
rm -rf "$S/debs" "$S/debs26" "$ROOT" # from scratch: a stale 24.04 libgbm or libwayland would shadow the system's
mkdir -p "$S/lists/partial" "$S/cache/archives/partial" "$S/etc/apt/sources.list.d" "$S/etc/apt/preferences.d" \
  "$S/debs" "$S/debs26" "$ROOT"
touch "$S/status"

echo "== WebKit (Ubuntu 24.04 build)"
(cd "$APP" && PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 npx playwright install webkit >/dev/null 2>&1 || true)

echo "== 24.04 libraries"
cat > "$S/etc/apt/sources.list" <<'LIST'
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] http://archive.ubuntu.com/ubuntu noble main universe
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] http://archive.ubuntu.com/ubuntu noble-updates main universe
LIST
APTO=(-o "Dir::Etc=$S/etc/apt" -o "Dir::Etc::sourcelist=$S/etc/apt/sources.list" -o "Dir::State::Lists=$S/lists"
      -o "Dir::Cache=$S/cache" -o "Dir::State::status=$S/status" -o Debug::NoLocking=1)
apt-get "${APTO[@]}" update -qq
(cd "$S/debs" && apt-get "${APTO[@]}" download -qq libgtk-4-1 libgraphene-1.0-0 libicu74 libxml2 libwoff1 libvpx9 \
  libevent-2.1-7t64 libwebpdemux2 libavif16 libharfbuzz-icu0 libenchant-2-2 libsecret-1-0 libhyphen0 libmanette-0.2-0 \
  libgles2 libgav1-1 libgudev-1.0-0 liborc-0.4-0t64 librav1e0 libsvtav1enc1d1 libyuv0 libabsl20220623t64 libdav1d7 \
  libaom3 libx265-199 libwebp7 libsharpyuv0)

echo "== 26.04 libraries (EGL, Wayland, GStreamer: must match the system's Mesa and GStreamer)"
(cd "$S/debs26" && apt-get download -qq libegl-mesa0 libegl1 libglvnd0 libwayland-server0 gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good libgstreamer-plugins-base1.0-0 libgstreamer-gl1.0-0 libgstreamer-plugins-bad1.0-0 \
  libgstreamer-plugins-extra1.0-0)

for d in "$S"/debs/*.deb "$S"/debs26/*.deb; do dpkg-deb -x "$d" "$ROOT"; done

echo "== MiniBrowser keeps LD_LIBRARY_PATH"
for w in "$HOME"/.cache/ms-playwright/webkit-*/minibrowser-wpe/MiniBrowser; do
  sed -i 's|^export LD_LIBRARY_PATH="${MYDIR}/lib:${MYDIR}/sys/lib"$|export LD_LIBRARY_PATH="${MYDIR}/lib:${MYDIR}/sys/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"|' "$w"
done

L="$ROOT/usr/lib/x86_64-linux-gnu"
missing=$(for w in "$HOME"/.cache/ms-playwright/webkit-*/minibrowser-wpe; do
  find "$w" -type f \( -name '*.so*' -o -perm -u+x \) -exec sh -c 'LD_LIBRARY_PATH="$0:$1/lib:$1/sys/lib" ldd "$2" 2>/dev/null' "$L" "$w" {} \;
done | grep 'not found' | sort -u || true)
if [ -n "$missing" ]; then echo "Still missing:"; echo "$missing"; exit 1; fi
echo "OK — KASKADE_WEBKIT_ROOT=$ROOT"
