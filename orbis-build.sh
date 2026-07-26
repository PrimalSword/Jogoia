#!/usr/bin/env bash
set -euo pipefail

VERSION="0.2.3"
ALPINE_VERSION="3.24.1"
ARCH="x86_64"
FLAVOR="extended"
IMAGE_NAME="orbisos-${VERSION}-${ARCH}"
WORKDIR="${PWD}/.orbis-build"
OUTDIR="${PWD}/dist"
BASE_ISO="${WORKDIR}/alpine-${FLAVOR}-${ALPINE_VERSION}-${ARCH}.iso"
BASE_SHA="${BASE_ISO}.sha256"
APKOVL="${WORKDIR}/orbis.apkovl.tar.gz"
BASE_URL="https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/${ARCH}"
CORE_DIR="${PWD}/orbis/core"
BUILD_COMMIT="${GITHUB_SHA:-$(git rev-parse HEAD 2>/dev/null || printf unknown)}"
BUILD_DATE="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

for command in curl xorriso tar sha256sum install; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Ferramenta ausente: $command" >&2
    exit 1
  }
done

for file in orbis orbis-wifi orbis-install orbis-update orbis-log; do
  [ -f "$CORE_DIR/$file" ] || {
    echo "Arquivo ausente: $CORE_DIR/$file" >&2
    exit 1
  }
done

rm -rf "$WORKDIR"
mkdir -p \
  "$WORKDIR/overlay/etc/apk" \
  "$WORKDIR/overlay/etc/network" \
  "$WORKDIR/overlay/etc/local.d" \
  "$WORKDIR/overlay/root" \
  "$WORKDIR/overlay/usr/local/bin" \
  "$WORKDIR/overlay/var/log" \
  "$OUTDIR"
rm -f "$OUTDIR"/orbisos-*.iso "$OUTDIR"/orbisos-*.iso.sha256

printf 'Baixando Alpine Extended %s...\n' "$ALPINE_VERSION"
curl --fail --location --retry 3 --output "$BASE_ISO" \
  "$BASE_URL/alpine-${FLAVOR}-${ALPINE_VERSION}-${ARCH}.iso"
curl --fail --location --retry 3 --output "$BASE_SHA" \
  "$BASE_URL/alpine-${FLAVOR}-${ALPINE_VERSION}-${ARCH}.iso.sha256"

(
  cd "$WORKDIR"
  sha256sum --check "$(basename "$BASE_SHA")"
)

printf 'orbis\n' > "$WORKDIR/overlay/etc/hostname"
: > "$WORKDIR/overlay/etc/motd"
printf 'OrbisOS %s iniciado.\n' "$VERSION" > "$WORKDIR/overlay/var/log/orbis.log"

cat > "$WORKDIR/overlay/etc/orbis-release" <<EOF
ORBIS_VERSION=$VERSION
ORBIS_BRANCH=main
ORBIS_COMMIT=$BUILD_COMMIT
ORBIS_REPOSITORY=https://github.com/PrimalSword/Jogoia.git
BUILD_DATE=$BUILD_DATE
EOF

cat > "$WORKDIR/overlay/etc/hosts" <<'EOF'
127.0.0.1 localhost
127.0.1.1 orbis
EOF

cat > "$WORKDIR/overlay/etc/network/interfaces" <<'EOF'
auto lo
iface lo inet loopback
EOF

cat > "$WORKDIR/overlay/etc/apk/repositories" <<'EOF'
https://dl-cdn.alpinelinux.org/alpine/v3.24/main
https://dl-cdn.alpinelinux.org/alpine/v3.24/community
EOF

cat > "$WORKDIR/overlay/etc/apk/world" <<'EOF'
alpine-base
alpine-conf
busybox
openrc
util-linux
pciutils
usbutils
e2fsprogs
parted
syslinux
linux-lts
linux-firmware-ath9k_htc
linux-firmware-realtek
linux-firmware-brcm
iw
wireless-tools
wpa_supplicant
wpa_supplicant-openrc
dhcpcd
curl
ca-certificates
git
openssh
python3
sqlite
nano
less
EOF

cat > "$WORKDIR/overlay/etc/inittab" <<'EOF'
::sysinit:/sbin/openrc sysinit
::sysinit:/sbin/openrc boot
::wait:/sbin/openrc default

tty1::respawn:/sbin/getty -n -l /usr/local/bin/orbis-login 38400 tty1

::ctrlaltdel:/sbin/reboot
::shutdown:/sbin/openrc shutdown
EOF

cat > "$WORKDIR/overlay/root/.profile" <<'EOF'
export HOSTNAME=orbis
export PS1='root@orbis:\w# '
alias status-orbis='orbis --status'
alias log-orbis='orbis-log'
EOF

cat > "$WORKDIR/overlay/usr/local/bin/orbis-login" <<'EOF'
#!/bin/sh
hostname orbis 2>/dev/null || true
mkdir -p /var/log
printf '%s OrbisOS iniciou em %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || printf boot)" "$(uname -r)" >> /var/log/orbis.log
/usr/local/bin/orbis --status
exec /bin/ash -l
EOF

for file in orbis orbis-wifi orbis-install orbis-update orbis-log; do
  install -m 0755 "$CORE_DIR/$file" "$WORKDIR/overlay/usr/local/bin/$file"
done
chmod +x "$WORKDIR/overlay/usr/local/bin/orbis-login"

tar --numeric-owner --owner=0 --group=0 -C "$WORKDIR/overlay" -czf "$APKOVL" .

printf 'Criando ISO OrbisOS %s...\n' "$VERSION"
xorriso -indev "$BASE_ISO" -outdev "$OUTDIR/${IMAGE_NAME}.iso" \
  -map "$APKOVL" /orbis.apkovl.tar.gz -boot_image any replay

sha256sum "$OUTDIR/${IMAGE_NAME}.iso" > "$OUTDIR/${IMAGE_NAME}.iso.sha256"
printf '\nImagem criada: %s\n' "$OUTDIR/${IMAGE_NAME}.iso"
printf 'Checksum:      %s\n' "$OUTDIR/${IMAGE_NAME}.iso.sha256"
