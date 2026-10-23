#!/bin/sh
# JogOia / Orbis: diagnóstico não destrutivo do navegador e da GPU.
set -u
echo "=== Sistema ==="
cat /etc/os-release 2>/dev/null | head -6
echo "=== Navegadores ==="
for b in firefox firefox-esr chromium chromium-browser; do
  if command -v "$b" >/dev/null 2>&1; then "$b" --version 2>&1 | head -1; fi
done
echo "=== Pacotes disponíveis ==="
if command -v apk >/dev/null 2>&1; then apk info -e firefox firefox-esr chromium mesa-vulkan-intel 2>/dev/null; fi
echo "=== Sessão gráfica ==="
printf 'DISPLAY=%s WAYLAND_DISPLAY=%s\n' "${DISPLAY:-}" "${WAYLAND_DISPLAY:-}"
echo "=== GPU ==="
if command -v lspci >/dev/null 2>&1; then lspci | grep -Ei 'vga|3d|display' || :; fi
if command -v glxinfo >/dev/null 2>&1; then glxinfo -B 2>/dev/null | grep -E 'OpenGL renderer|OpenGL version' || :; fi
echo "=== Arquivos de configuração do JogOia ==="
find /etc /opt /usr/local -maxdepth 3 \( -iname '*orbis*' -o -iname '*jogoia*' \) 2>/dev/null | head -40
echo "Diagnóstico concluído. Nenhuma configuração foi alterada."
