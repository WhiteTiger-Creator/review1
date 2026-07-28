#!/usr/bin/env bash
set -euo pipefail

build_root="$(mktemp -d /tmp/arena-oracle.XXXXXX)"
trap 'rm -rf -- "$build_root"' EXIT

mkdir -p "$build_root/package" "$build_root/assets"
cp /solution/vendor/solution-vendor.tar.gz \
   /solution/vendor/SHA256SUMS \
   "$build_root/package/"
(
    cd "$build_root/package"
    sha256sum -c SHA256SUMS
)
tar --no-same-owner -xzf "$build_root/package/solution-vendor.tar.gz" \
    -C "$build_root/assets"

mkdir -p "$build_root/engine-package" "$build_root/engine-vendor" \
    "$build_root/fairy-stockfish" "$build_root/native-package" \
    "$build_root/oracle-source"
cp "$build_root/assets/engine/fairy-stockfish-vendor.tar.gz" \
   "$build_root/assets/engine/SHA256SUMS" \
   "$build_root/engine-package/"
(
    cd "$build_root/engine-package"
    sha256sum -c SHA256SUMS
)
tar --no-same-owner -xzf \
    "$build_root/engine-package/fairy-stockfish-vendor.tar.gz" \
    -C "$build_root/engine-vendor"
(
    cd "$build_root/engine-vendor"
    sha256sum -c SHA256SUMS
)
tar --no-same-owner -xzf "$build_root/engine-vendor/fairy_sf_14.tar.gz" \
    --strip-components=1 -C "$build_root/fairy-stockfish"
patch --batch --forward -d "$build_root/fairy-stockfish" -p1 \
    < "$build_root/engine-vendor/timeman-identifier.patch"

cp "$build_root/assets/native/oracle_source.tar.gz" \
   "$build_root/assets/native/SHA256SUMS" \
   "$build_root/native-package/"
(
    cd "$build_root/native-package"
    sha256sum -c SHA256SUMS
)
tar --no-same-owner -xzf "$build_root/native-package/oracle_source.tar.gz" \
    -C "$build_root/oracle-source"

case "$(uname -m)" in
    x86_64|amd64) fairy_arch=general-64 ;;
    aarch64|arm64) fairy_arch=armv8 ;;
    *)
        printf 'Unsupported Fairy-Stockfish build architecture: %s\n' \
            "$(uname -m)" >&2
        exit 1
        ;;
esac
if ! make -C "$build_root/fairy-stockfish/src" -j1 build \
    ARCH="$fairy_arch" nnue=no optimize=no largeboards=yes all=yes \
    EXTRACXXFLAGS='-O2' \
    >"$build_root/engine-build.log" 2>&1; then
    cat "$build_root/engine-build.log" >&2
    exit 1
fi
install -m 0755 "$build_root/fairy-stockfish/src/stockfish" \
    "$build_root/oracle-fairy-stockfish"

g++ -std=c++20 -O2 -DNDEBUG -Wall -Wextra -Werror -Wpedantic \
    "$build_root/oracle-source/oracle_player.cpp" \
    -o "$build_root/oracle-player"

if ! ORACLE_ENGINE="$build_root/oracle-fairy-stockfish" \
    ORACLE_VARIANT="kyotoshogi" \
    ORACLE_PROTOCOL="arena-kyoto-shogi-v1" \
    ORACLE_NODES="100000" \
    ORACLE_MAX_TURNS="512" \
    "$build_root/oracle-player" >"$build_root/oracle-result.log" 2>&1; then
    cat "$build_root/oracle-result.log" >&2
    exit 1
fi

cat "$build_root/oracle-result.log"
grep -q '^ORACLE_FAIRY_VARIANT_WIN variant=kyotoshogi ' \
    "$build_root/oracle-result.log"
