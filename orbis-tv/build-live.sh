#!/usr/bin/env bash
set -euo pipefail

VERSION="${ORBIS_TV_VERSION:-0.2.0}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/.orbistv-build"
OUT_DIR="$ROOT_DIR/dist"
IMAGE_BASENAME="orbistv-${VERSION}-amd64"

if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    exec sudo -E "$0" "$@"
  fi
  echo "Execute como root." >&2
  exit 1
fi

for cmd in lb debootstrap xorriso sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Ferramenta ausente: $cmd" >&2
    exit 1
  }
done

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$OUT_DIR"
cd "$BUILD_DIR"

# v0.2: imagem deliberadamente conservadora para o Acer Z5WAH/LA-B161P.
# Usamos Debian 12 (Bookworm) e SOMENTE SYSLINUX/ISOLINUX no boot.
# Isso remove o GRUB/UEFI do caminho de inicialização, pois o firmware antigo
# do Acer reiniciou ao tentar iniciar a v0.1 pelo pendrive, inclusive em modo DD.
lb config noauto \
  --mode debian \
  --distribution bookworm \
  --architectures amd64 \
  --binary-images iso-hybrid \
  --bootloaders syslinux \
  --archive-areas "main contrib non-free non-free-firmware" \
  --security false \
  --bootappend-live "boot=live components username=orbis hostname=orbistv locales=pt_BR.UTF-8 keyboard-layouts=br timezone=America/Sao_Paulo quiet" \
  --apt-recommends true \
  --memtest none \
  --iso-application "Orbis TV" \
  --iso-publisher "Jogoia / Orbis TV" \
  --iso-volume "ORBIS_TV"

mkdir -p config/package-lists
cat > config/package-lists/orbis-tv.list.chroot <<'EOF'
linux-image-amd64
live-boot
live-config
systemd-sysv
sudo
locales
console-setup
keyboard-configuration
xserver-xorg
xserver-xorg-core
xserver-xorg-legacy
xinit
x11-xserver-utils
xinput
openbox
xterm
xbindkeys
dbus-x11
kodi
kodi-repository-kodi
firefox-esr
firefox-esr-l10n-pt-br
network-manager
wpasupplicant
wireless-tools
rfkill
alsa-utils
pulseaudio
pavucontrol
mesa-utils
mesa-va-drivers
i965-va-driver
vainfo
intel-microcode
firmware-iwlwifi
firmware-realtek
firmware-atheros
firmware-brcm80211
firmware-misc-nonfree
curl
ca-certificates
git
nano
htop
python3
fonts-dejavu-core
fonts-noto-core
unclutter-xfixes
EOF

# Arquivos persistentes do live system.
mkdir -p \
  config/includes.chroot/etc/systemd/system/getty@tty1.service.d \
  config/includes.chroot/etc/X11 \
  config/includes.chroot/etc/sudoers.d \
  config/includes.chroot/etc/skel/.config/openbox \
  config/includes.chroot/etc/skel/.kodi/addons/plugin.program.orbis \
  config/includes.chroot/etc/skel/.kodi/userdata \
  config/includes.chroot/usr/local/bin \
  config/includes.chroot/usr/local/share/orbis-tv

cat > config/includes.chroot/etc/systemd/system/getty@tty1.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin orbis --noclear %I $TERM
Type=idle
EOF

cat > config/includes.chroot/etc/X11/Xwrapper.config <<'EOF'
allowed_users=console
needs_root_rights=yes
EOF

cat > config/includes.chroot/etc/sudoers.d/orbis-tv <<'EOF'
orbis ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff, /usr/bin/systemctl reboot, /usr/bin/nmtui, /usr/sbin/reboot, /usr/sbin/poweroff
EOF
chmod 0440 config/includes.chroot/etc/sudoers.d/orbis-tv

cat > config/includes.chroot/etc/skel/.profile <<'EOF'
export LIBVA_DRIVER_NAME=i965
export MOZ_ENABLE_WAYLAND=0
export ORBIS_TV=1

if [ -z "${DISPLAY:-}" ] && [ "$(tty 2>/dev/null || true)" = "/dev/tty1" ]; then
  exec startx
fi
EOF

cat > config/includes.chroot/etc/skel/.xinitrc <<'EOF'
#!/bin/sh
set -u

export LIBVA_DRIVER_NAME=i965
export MOZ_ENABLE_WAYLAND=0
export XDG_CURRENT_DESKTOP=OPENBOX

xset -dpms >/dev/null 2>&1 || true
xset s off >/dev/null 2>&1 || true
xset s noblank >/dev/null 2>&1 || true
/usr/local/bin/orbis-display || true
pulseaudio --start >/dev/null 2>&1 || true

if command -v dbus-run-session >/dev/null 2>&1; then
  exec dbus-run-session -- /usr/local/bin/orbis-session
else
  exec /usr/local/bin/orbis-session
fi
EOF
chmod 0755 config/includes.chroot/etc/skel/.xinitrc

cat > config/includes.chroot/usr/local/bin/orbis-display <<'EOF'
#!/bin/sh
set -u

out="$(xrandr --query 2>/dev/null | awk '$2=="connected" {print $1}' | grep -E '^(VGA|HDMI|DP|DVI)' | head -n1 || true)"
[ -n "$out" ] || out="$(xrandr --query 2>/dev/null | awk '$2=="connected" {print $1; exit}' || true)"
[ -n "$out" ] || exit 0

for internal in $(xrandr --query 2>/dev/null | awk '$2=="connected" {print $1}' | grep -E '^(LVDS|eDP|DSI)' || true); do
  [ "$internal" = "$out" ] || xrandr --output "$internal" --off >/dev/null 2>&1 || true
done

if xrandr --query 2>/dev/null | awk -v o="$out" '
  $1==o && $2=="connected" {inside=1; next}
  inside && $1 ~ /^[A-Za-z]/ {inside=0}
  inside && $1=="800x600" {found=1}
  END {exit found?0:1}'; then
  xrandr --output "$out" --mode 800x600 --primary --pos 0x0 >/dev/null 2>&1 || true
elif xrandr --query 2>/dev/null | grep -q '^[[:space:]]*640x480'; then
  xrandr --output "$out" --mode 640x480 --primary --pos 0x0 >/dev/null 2>&1 || true
else
  xrandr --output "$out" --auto --primary --pos 0x0 >/dev/null 2>&1 || true
fi
EOF
chmod 0755 config/includes.chroot/usr/local/bin/orbis-display

cat > config/includes.chroot/usr/local/bin/orbis-browser <<'EOF'
#!/bin/sh
set -u
url="${1:-file:///usr/local/share/orbis-tv/browser-home.html}"
export MOZ_ENABLE_WAYLAND=0
export LIBVA_DRIVER_NAME=i965
exec firefox-esr --new-instance --kiosk "$url"
EOF
chmod 0755 config/includes.chroot/usr/local/bin/orbis-browser

cat > config/includes.chroot/usr/local/bin/orbis-session <<'EOF'
#!/bin/sh
set -u

openbox-session >/tmp/orbis-openbox.log 2>&1 &
OPENBOX_PID=$!
trap 'kill "$OPENBOX_PID" 2>/dev/null || true' EXIT INT TERM HUP
sleep 1

# Kodi é a interface principal, como uma TV box. Se ele fechar, volta ao console.
exec kodi --standalone
EOF
chmod 0755 config/includes.chroot/usr/local/bin/orbis-session

cat > config/includes.chroot/etc/skel/.config/openbox/rc.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <keyboard>
    <keybind key="C-A-b">
      <action name="Execute"><command>/usr/local/bin/orbis-browser</command></action>
    </keybind>
    <keybind key="C-A-w">
      <action name="Execute"><command>xterm -fullscreen -e nmtui</command></action>
    </keybind>
    <keybind key="C-A-t">
      <action name="Execute"><command>xterm</command></action>
    </keybind>
  </keyboard>
  <applications>
    <application class="Firefox-esr"><decor>no</decor><maximized>true</maximized></application>
  </applications>
</openbox_config>
EOF

cat > config/includes.chroot/usr/local/share/orbis-tv/browser-home.html <<'EOF'
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orbis TV</title>
<style>
  :root { font-family: system-ui, sans-serif; color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; background:radial-gradient(circle at 20% 10%,#24304b,#0b0f18 55%); color:#fff; padding:6vh 6vw; overflow:hidden; }
  h1 { margin:0 0 1vh; font-size:7vh; letter-spacing:-.04em; }
  p { margin:0 0 5vh; color:#aeb8cc; font-size:2.5vh; }
  .grid { display:grid; grid-template-columns:repeat(3,1fr); gap:2vw; }
  a,button { border:0; text-decoration:none; color:#fff; background:#20283a; border-radius:2vh; padding:4vh 2vw; font-size:3.2vh; font-weight:700; min-height:18vh; display:flex; align-items:flex-end; box-shadow:0 1vh 3vh #0007; outline:none; }
  a:focus,button:focus { transform:scale(1.055); background:#3b4b70; box-shadow:0 0 0 .6vh #fff,0 2vh 5vh #0009; }
  .sub { display:block; font-size:1.8vh; font-weight:400; color:#c5ccda; margin-top:1vh; }
</style>
</head>
<body>
<h1>Orbis TV</h1>
<p>Navegação simples para a Samsung CRT.</p>
<div class="grid">
  <a href="https://www.youtube.com/">YouTube</a>
  <a href="https://www.google.com/">Pesquisar</a>
  <button id="url">Abrir endereço<span class="sub">Digite qualquer site</span></button>
  <a href="about:blank">Página vazia</a>
  <a href="file:///usr/local/share/orbis-tv/browser-home.html">Início</a>
  <button onclick="window.close()">Voltar ao Kodi</button>
</div>
<script>
const items=[...document.querySelectorAll('a,button')]; let i=0; items[0].focus();
function go(n){ i=(n+items.length)%items.length; items[i].focus(); }
document.addEventListener('keydown',e=>{ if(e.key==='ArrowRight'){go(i+1);e.preventDefault()} if(e.key==='ArrowLeft'){go(i-1);e.preventDefault()} if(e.key==='ArrowDown'){go(i+3);e.preventDefault()} if(e.key==='ArrowUp'){go(i-3);e.preventDefault()} });
document.getElementById('url').onclick=()=>{ let u=prompt('Endereço do site:','https://'); if(u){ if(!/^https?:\/\//i.test(u))u='https://'+u; location.href=u; } };
</script>
</body>
</html>
EOF

cat > config/includes.chroot/etc/skel/.kodi/addons/plugin.program.orbis/addon.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="plugin.program.orbis" name="Orbis Apps" version="0.2.0" provider-name="Orbis TV">
  <requires>
    <import addon="xbmc.python" version="3.0.0"/>
  </requires>
  <extension point="xbmc.python.pluginsource" library="default.py">
    <provides>executable</provides>
  </extension>
  <extension point="xbmc.addon.metadata">
    <summary lang="pt_BR">Atalhos do Orbis TV</summary>
    <description lang="pt_BR">Navegador, Wi-Fi, terminal e energia.</description>
    <platform>linux</platform>
  </extension>
</addon>
EOF

cat > config/includes.chroot/etc/skel/.kodi/addons/plugin.program.orbis/default.py <<'EOF'
import subprocess
import sys
import urllib.parse
import xbmcgui
import xbmcplugin

HANDLE = int(sys.argv[1])
BASE = sys.argv[0]
params = urllib.parse.parse_qs(sys.argv[2].lstrip('?')) if len(sys.argv) > 2 else {}
action = params.get('action', [''])[0]

if action:
    if action == 'browser':
        subprocess.Popen(['/usr/local/bin/orbis-browser'])
    elif action == 'wifi':
        subprocess.Popen(['xterm', '-fullscreen', '-e', 'nmtui'])
    elif action == 'terminal':
        subprocess.Popen(['xterm', '-fullscreen'])
    elif action == 'reboot':
        subprocess.Popen(['sudo', 'systemctl', 'reboot'])
    elif action == 'poweroff':
        subprocess.Popen(['sudo', 'systemctl', 'poweroff'])
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
else:
    entries = [
        ('Navegador', 'browser'),
        ('Wi-Fi / Rede', 'wifi'),
        ('Terminal', 'terminal'),
        ('Reiniciar', 'reboot'),
        ('Desligar', 'poweroff'),
    ]
    for label, name in entries:
        item = xbmcgui.ListItem(label=label)
        item.setProperty('IsPlayable', 'false')
        url = BASE + '?' + urllib.parse.urlencode({'action': name})
        xbmcplugin.addDirectoryItem(HANDLE, url, item, isFolder=False)
    xbmcplugin.endOfDirectory(HANDLE)
EOF

cat > config/includes.chroot/etc/skel/.kodi/userdata/favourites.xml <<'EOF'
<favourites>
  <favourite name="Orbis Apps">ActivateWindow(Programs,"plugin://plugin.program.orbis/",return)</favourite>
</favourites>
EOF

# Um hook para habilitar rede e garantir permissões antes de compactar o live system.
mkdir -p config/hooks/live
cat > config/hooks/live/010-orbis-tv.hook.chroot <<'EOF'
#!/bin/sh
set -e
systemctl enable NetworkManager.service >/dev/null 2>&1 || true
chmod 0755 /usr/local/bin/orbis-display /usr/local/bin/orbis-browser /usr/local/bin/orbis-session
chmod 0755 /etc/skel/.xinitrc
chmod 0440 /etc/sudoers.d/orbis-tv
# pt_BR.UTF-8 disponível desde o primeiro boot.
grep -q '^pt_BR.UTF-8 UTF-8' /etc/locale.gen 2>/dev/null || echo 'pt_BR.UTF-8 UTF-8' >> /etc/locale.gen
locale-gen >/dev/null 2>&1 || true
EOF
chmod 0755 config/hooks/live/010-orbis-tv.hook.chroot

lb build

ISO="$(find . -maxdepth 1 -type f \( -name '*.hybrid.iso' -o -name '*.iso' \) | head -n1)"
[ -n "$ISO" ] || { echo "ISO não encontrada após o build." >&2; exit 1; }

cp "$ISO" "$OUT_DIR/${IMAGE_BASENAME}.iso"
sha256sum "$OUT_DIR/${IMAGE_BASENAME}.iso" > "$OUT_DIR/${IMAGE_BASENAME}.iso.sha256"
chown "${SUDO_UID:-0}:${SUDO_GID:-0}" "$OUT_DIR/${IMAGE_BASENAME}.iso" "$OUT_DIR/${IMAGE_BASENAME}.iso.sha256" 2>/dev/null || true

printf '\nOrbis TV criado:\n  %s\n' "$OUT_DIR/${IMAGE_BASENAME}.iso"
