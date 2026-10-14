#!/usr/bin/env bash
# Installs the OTel Weaver release pinned in versions.env, after checking the
# download against the checksum pinned there.
#
#   tools/install_weaver.sh [<dir>]       install to <dir>/weaver (default .weaver/bin)
#   tools/install_weaver.sh --print-checksums
#                                         print the checksum lines for the
#                                         pinned version, to paste into
#                                         versions.env after a bump
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=/dev/null
source "$root/versions.env"
release="https://github.com/open-telemetry/weaver/releases/download/$WEAVER_VERSION"

if [[ "${1:-}" == "--print-checksums" ]]; then
  for target in x86_64-unknown-linux-gnu aarch64-unknown-linux-gnu x86_64-apple-darwin aarch64-apple-darwin; do
    sum=$(curl -fsSL "$release/sha256.sum" | awk -v f="*weaver-$target.tar.xz" '$2 == f {print $1}')
    var=$(tr 'a-z-' 'A-Z_' <<<"$target")
    echo "WEAVER_SHA256_$var=$sum"
  done
  exit 0
fi

dest=${1:-$root/.weaver/bin}
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) target=x86_64-unknown-linux-gnu ;;
  Linux-aarch64 | Linux-arm64) target=aarch64-unknown-linux-gnu ;;
  Darwin-x86_64) target=x86_64-apple-darwin ;;
  Darwin-arm64) target=aarch64-apple-darwin ;;
  *) echo "no pinned Weaver build for $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac
var="WEAVER_SHA256_$(tr 'a-z-' 'A-Z_' <<<"$target")"
want=${!var:-}
if [[ -z "$want" ]]; then
  echo "versions.env pins no checksum for $target ($var)" >&2
  exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
archive="weaver-$target.tar.xz"
curl -fsSL -o "$tmp/$archive" "$release/$archive"
got=$(shasum -a 256 "$tmp/$archive" | awk '{print $1}')
if [[ "$got" != "$want" ]]; then
  echo "checksum mismatch for $archive ($WEAVER_VERSION): got $got, versions.env pins $want" >&2
  echo "after a version bump, run: tools/install_weaver.sh --print-checksums" >&2
  exit 1
fi
tar -xJf "$tmp/$archive" -C "$tmp"
mkdir -p "$dest"
install -m 0755 "$tmp/weaver-$target/weaver" "$dest/weaver"
"$dest/weaver" --version
