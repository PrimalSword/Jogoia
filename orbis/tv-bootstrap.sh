#!/bin/sh
set -eu

RAW_BASE="https://raw.githubusercontent.com/PrimalSword/Jogoia/main"
TARGET="/usr/local/bin/orbis-tv"

echo 'ORBIS TV  •  BOOTSTRAP'
echo '─────────────────────────────────────────────'

[ "$(id -u)" -eq 0 ] || { echo 'Execute como root.'; exit 1; }

mkdir -p /usr/local/bin /etc/apk /var/log

if command -v orbis-update >/dev/null 2>&1; then
  echo 'Atualizando OrbisOS pelo repositório...'
  if ! orbis-update; then
    echo 'Aviso: orbis-update falhou; vou instalar o modo TV diretamente mesmo assim.'
  fi
fi

if [ ! -x "$TARGET" ]; then
  command -v curl >/dev/null 2>&1 || {
    grep -Eq '^[^#].*/v3\.24/main([[:space:]]*)$' /etc/apk/repositories 2>/dev/null || printf '%s\n' 'https://dl-cdn.alpinelinux.org/alpine/v3.24/main' >> /etc/apk/repositories
    grep -Eq '^[^#].*/v3\.24/community([[:space:]]*)$' /etc/apk/repositories 2>/dev/null || printf '%s\n' 'https://dl-cdn.alpinelinux.org/alpine/v3.24/community' >> /etc/apk/repositories
    apk update
    apk add --force-broken-world curl ca-certificates
  }
  tmp="$TARGET.tmp.$$"
  curl --fail --location --retry 3 "$RAW_BASE/orbis/core/orbis-tv" -o "$tmp"
  chmod 0755 "$tmp"
  mv -f "$tmp" "$TARGET"
fi

echo 'Instalando o ambiente gráfico mínimo...'
"$TARGET" --prepare

echo
echo 'Pronto.'
echo 'Para usar:'
echo '  orbis-tv'
echo 'ou:'
echo '  orbis-tv https://seu-site.example'
