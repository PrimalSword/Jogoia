#!/bin/sh
set -eu

[ "$(id -u)" -eq 0 ] || { echo "Execute com sudo: sudo bash orbis/install.sh"; exit 1; }

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

have() { command -v "$1" >/dev/null 2>&1; }

printf '%s\n' '[1/7] Verificando dependências essenciais...'
missing=""
have python3 || missing="$missing python3"
have git || missing="$missing git"
have curl || missing="$missing curl"
have sqlite3 || missing="$missing sqlite3"

if [ -n "$missing" ]; then
  printf 'Dependências ausentes:%s\n' "$missing"
  printf '%s\n' 'Tentando instalar apenas o necessário, sem tmux, htop ou pacotes ligados ao systemd...'
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $missing ca-certificates
fi

printf '%s\n' '[2/7] Criando usuário e diretórios...'
if ! id orbis >/dev/null 2>&1; then
  useradd --system --home /var/lib/orbis --shell /usr/sbin/nologin orbis
fi
install -d -m 0755 /opt/orbis /etc/orbis /var/log/orbis
install -d -o orbis -g orbis -m 0755 /var/lib/orbis
chown orbis:orbis /var/log/orbis

if [ ! -f /etc/orbis/secrets.env ]; then
  install -m 0600 /dev/null /etc/orbis/secrets.env
fi

printf '%s\n' '[3/7] Instalando Orbis Core...'
install -m 0755 "$BASE_DIR/orbisd.py" /opt/orbis/orbisd.py
install -m 0755 "$BASE_DIR/orbis-status" /usr/local/bin/orbis-status
install -m 0755 "$BASE_DIR/orbis-mode" /usr/local/bin/orbis-mode
install -m 0644 "$BASE_DIR/profile.sh" /etc/profile.d/orbis.sh

printf '%s\n' '[4/7] Configurando serviço runit...'
install -d -m 0755 /etc/sv/orbisd
install -m 0755 "$BASE_DIR/service/run" /etc/sv/orbisd/run
mkdir -p /var/service
ln -sfn /etc/sv/orbisd /var/service/orbisd

printf '%s\n' '[5/7] Preparando acesso remoto...'
if [ -d /etc/sv/ssh ]; then
  ln -sfn /etc/sv/ssh /var/service/ssh
elif [ -d /etc/sv/sshd ]; then
  ln -sfn /etc/sv/sshd /var/service/sshd
else
  printf '%s\n' 'Aviso: serviço SSH não encontrado. O Orbis Core continuará funcionando localmente.'
fi

printf '%s\n' '[6/7] Reduzindo escritas desnecessárias no cartão...'
if [ -f /etc/fstab ]; then
  if [ ! -f /etc/fstab.orbis-backup ]; then
    cp -a /etc/fstab /etc/fstab.orbis-backup
  fi
  if ! grep -q '^tmpfs[[:space:]]\+/tmp' /etc/fstab; then
    printf '%s\n' 'tmpfs /tmp tmpfs defaults,noatime,nosuid,nodev,mode=1777,size=128M 0 0' >> /etc/fstab
  fi
  swapoff -a 2>/dev/null || true
  sed -i '/^[^#].*[[:space:]]swap[[:space:]]/ s/^/# Orbis disabled: /' /etc/fstab
fi

printf '%s\n' '[7/7] Iniciando serviço...'
sv up orbisd 2>/dev/null || true
sleep 2

cat <<'EOF'

OrbisOS Core instalado.

Teste agora:
  orbis-status
  sudo sv status orbisd

Mantenha o desktop nesta primeira inicialização.
Quando confirmarmos rede e serviço:
  sudo orbis-mode terminal
  sudo reboot

Para restaurar:
  sudo orbis-mode desktop
  sudo reboot
EOF
