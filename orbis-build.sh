#!/usr/bin/env bash
set -euo pipefail

VERSION="0.1.0"
ARCH="amd64"
DIST="bookworm"
IMAGE_NAME="orbisos-${VERSION}-${ARCH}"
WORKDIR="${PWD}/.orbis-live"
OUTDIR="${PWD}/dist"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute com sudo: sudo ./orbis-build.sh" >&2
  exit 1
fi

for command in lb debootstrap xorriso; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Ferramenta ausente: $command" >&2
    echo "Instale com: apt-get update && apt-get install -y live-build debootstrap xorriso isolinux syslinux-common" >&2
    exit 1
  }
done

rm -rf "$WORKDIR"
mkdir -p "$WORKDIR" "$OUTDIR"
cd "$WORKDIR"

lb config noauto \
  --mode debian \
  --distribution "$DIST" \
  --architectures "$ARCH" \
  --binary-images iso-hybrid \
  --bootappend-live "boot=live components quiet hostname=orbis username=orbis" \
  --debian-installer none \
  --archive-areas "main contrib non-free-firmware" \
  --apt-recommends false \
  --security false \
  --memtest none \
  --iso-application "OrbisOS" \
  --iso-publisher "Orbis Project" \
  --iso-volume "ORBISOS_01"

mkdir -p config/package-lists
cat > config/package-lists/orbis.list.chroot <<'EOF'
linux-image-amd64
live-boot
live-config
live-config-systemd
systemd-sysv
bash
busybox
coreutils
util-linux
iproute2
iputils-ping
isc-dhcp-client
iw
wpasupplicant
wireless-tools
firmware-linux-free
firmware-iwlwifi
firmware-realtek
firmware-atheros
ca-certificates
curl
git
openssh-server
python3
python3-minimal
sqlite3
nano
less
htop
procps
pciutils
usbutils
EOF

mkdir -p config/includes.chroot/etc config/includes.chroot/usr/local/bin config/includes.chroot/etc/systemd/system/getty@tty1.service.d config/includes.chroot/etc/systemd/system

echo "orbis" > config/includes.chroot/etc/hostname
cat > config/includes.chroot/etc/hosts <<'EOF'
127.0.0.1 localhost
127.0.1.1 orbis
EOF

cat > config/includes.chroot/usr/local/bin/orbis <<'EOF'
#!/usr/bin/env python3
from __future__ import annotations

import platform
import shutil
import socket
import subprocess


def read_mem_mb() -> int:
    try:
        with open('/proc/meminfo', encoding='utf-8') as handle:
            for line in handle:
                if line.startswith('MemTotal:'):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def network_state() -> str:
    try:
        socket.create_connection(('1.1.1.1', 53), timeout=1.5).close()
        return 'CONECTADA'
    except OSError:
        return 'DESCONECTADA'


def disk_free() -> str:
    usage = shutil.disk_usage('/')
    return f"{usage.free // (1024 ** 2)} MB livres"


def ip_addresses() -> str:
    try:
        output = subprocess.check_output(['hostname', '-I'], text=True, timeout=2).strip()
        return output or 'sem endereço'
    except (OSError, subprocess.SubprocessError):
        return 'indisponível'


print('=' * 52)
print('                     ORBIS OS')
print('                    versão 0.1')
print('=' * 52)
print(f"Nó.............. {platform.node()}")
print(f"Processador..... {platform.machine()} / {platform.processor() or 'Linux'}")
print(f"Memória......... {read_mem_mb()} MB")
print(f"Armazenamento... {disk_free()}")
print(f"Rede............ {network_state()}")
print(f"IP.............. {ip_addresses()}")
print(f"Python.......... {platform.python_version()}")
print()
print('Orbis Core pronto. Terminal liberado.')
EOF
chmod +x config/includes.chroot/usr/local/bin/orbis

cat > config/includes.chroot/etc/systemd/system/getty@tty1.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I $TERM
Type=idle
EOF

cat > config/includes.chroot/etc/systemd/system/orbis-banner.service <<'EOF'
[Unit]
Description=OrbisOS terminal banner
After=getty@tty1.service

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'printf "\\033[2J\\033[H" > /dev/tty1; /usr/local/bin/orbis > /dev/tty1'
StandardInput=tty
TTYPath=/dev/tty1
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

mkdir -p config/hooks/live
cat > config/hooks/live/010-orbis.hook.chroot <<'EOF'
#!/bin/sh
set -eu
systemctl enable ssh.service
systemctl enable orbis-banner.service
printf '\n# OrbisOS\nexport PS1="\\[\\e[1;36m\\]root@orbis\\[\\e[0m\\]:\\w# "\nalias status-orbis="orbis"\n' >> /root/.bashrc
passwd -d root
EOF
chmod +x config/hooks/live/010-orbis.hook.chroot

lb build

ISO_PATH="$(find . -maxdepth 1 -type f \( -name 'live-image-*.hybrid.iso' -o -name 'live-image-*.iso' \) | head -n 1)"
if [[ -z "$ISO_PATH" ]]; then
  echo "A ISO não foi encontrada após o build." >&2
  exit 1
fi

cp "$ISO_PATH" "$OUTDIR/${IMAGE_NAME}.iso"
sha256sum "$OUTDIR/${IMAGE_NAME}.iso" > "$OUTDIR/${IMAGE_NAME}.iso.sha256"

echo
printf 'Imagem criada: %s\n' "$OUTDIR/${IMAGE_NAME}.iso"
printf 'Checksum:      %s\n' "$OUTDIR/${IMAGE_NAME}.iso.sha256"
