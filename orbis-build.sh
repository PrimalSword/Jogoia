#!/usr/bin/env bash
set -euo pipefail

VERSION="0.1.0"
ALPINE_VERSION="3.24.1"
ARCH="x86_64"
IMAGE_NAME="orbisos-${VERSION}-${ARCH}"
WORKDIR="${PWD}/.orbis-build"
OUTDIR="${PWD}/dist"
BASE_ISO="${WORKDIR}/alpine-standard-${ALPINE_VERSION}-${ARCH}.iso"
BASE_SHA="${BASE_ISO}.sha256"
APKOVL="${WORKDIR}/orbis.apkovl.tar.gz"
BASE_URL="https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/${ARCH}"

for command in curl xorriso tar sha256sum; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Ferramenta ausente: $command" >&2
    exit 1
  }
done

rm -rf "$WORKDIR"
mkdir -p "$WORKDIR/overlay/etc" "$WORKDIR/overlay/usr/local/bin" "$OUTDIR"
rm -f "$OUTDIR/${IMAGE_NAME}.iso" "$OUTDIR/${IMAGE_NAME}.iso.sha256"

printf 'Baixando a base oficial do Alpine Linux %s...\n' "$ALPINE_VERSION"
curl --fail --location --retry 3 \
  --output "$BASE_ISO" \
  "$BASE_URL/alpine-standard-${ALPINE_VERSION}-${ARCH}.iso"
curl --fail --location --retry 3 \
  --output "$BASE_SHA" \
  "$BASE_URL/alpine-standard-${ALPINE_VERSION}-${ARCH}.iso.sha256"

(
  cd "$WORKDIR"
  sha256sum --check "$(basename "$BASE_SHA")"
)

cat > "$WORKDIR/overlay/etc/hostname" <<'EOF'
orbis
EOF

cat > "$WORKDIR/overlay/etc/motd" <<'EOF'
EOF

cat > "$WORKDIR/overlay/etc/inittab" <<'EOF'
::sysinit:/sbin/openrc sysinit
::sysinit:/sbin/openrc boot
::wait:/sbin/openrc default

tty1::respawn:/sbin/getty -n -l /usr/local/bin/orbis-login 38400 tty1

::ctrlaltdel:/sbin/reboot
::shutdown:/sbin/openrc shutdown
EOF

cat > "$WORKDIR/overlay/usr/local/bin/orbis-login" <<'EOF'
#!/bin/sh
clear
/usr/local/bin/orbis
exec /bin/ash -l
EOF

cat > "$WORKDIR/overlay/usr/local/bin/orbis" <<'EOF'
#!/bin/sh
MEM_MB="$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || printf '?')"
CPU="$(awk -F: '/model name/ {gsub(/^[ \t]+/, "", $2); print $2; exit}' /proc/cpuinfo 2>/dev/null)"
[ -n "$CPU" ] || CPU="$(uname -m)"
IP="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | paste -sd, -)"
[ -n "$IP" ] || IP="desconectada"

printf '\n'
printf '=============================================\n'
printf '                  ORBIS OS                   \n'
printf '                  versão 0.1                \n'
printf '=============================================\n'
printf 'Sistema....... iniciado\n'
printf 'Processador... %s\n' "$CPU"
printf 'Memória....... %s MB\n' "$MEM_MB"
printf 'Rede.......... %s\n' "$IP"
printf 'Terminal...... pronto\n'
printf '=============================================\n'
printf '\n'
EOF

chmod +x \
  "$WORKDIR/overlay/usr/local/bin/orbis" \
  "$WORKDIR/overlay/usr/local/bin/orbis-login"

# O Alpine carrega automaticamente arquivos *.apkovl.tar.gz encontrados na mídia.
tar --numeric-owner --owner=0 --group=0 \
  -C "$WORKDIR/overlay" \
  -czf "$APKOVL" .

printf 'Criando a ISO do OrbisOS sem mount, chroot ou privilégios especiais...\n'
xorriso \
  -indev "$BASE_ISO" \
  -outdev "$OUTDIR/${IMAGE_NAME}.iso" \
  -map "$APKOVL" /orbis.apkovl.tar.gz \
  -boot_image any replay

sha256sum "$OUTDIR/${IMAGE_NAME}.iso" > "$OUTDIR/${IMAGE_NAME}.iso.sha256"

printf '\nImagem criada: %s\n' "$OUTDIR/${IMAGE_NAME}.iso"
printf 'Checksum:      %s\n' "$OUTDIR/${IMAGE_NAME}.iso.sha256"
