#!/bin/sh
set -eu

[ "$(id -u)" -eq 0 ] || { echo "Execute com sudo: sudo bash orbis/install.sh"; exit 1; }

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

echo "[1/7] Instalando dependências mínimas..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  python3 openssh-server git curl ca-certificates sqlite3 tmux htop rsync

echo "[2/7] Criando usuário e diretórios..."
if ! id orbis >/dev/null 2>&1; then
  useradd --system --home /var/lib/orbis --shell /usr/sbin/nologin orbis
fi
install -d -m 0755 /opt/orbis /etc/orbis /var/log/orbis
install -d -o orbis -g orbis -m 0755 /var/lib/orbis
chown orbis:orbis /var/log/orbis

if [ ! -f /etc/orbis/secrets.env ]; then
  install -m 0600 /dev/null /etc/orbis/secrets.env
fi

echo "[3/7] Instalando Orbis Core..."
install -m 0755 "$BASE_DIR/orbisd.py" /opt/orbis/orbisd.py
install -m 0755 "$BASE_DIR/orbis-status" /usr/local/bin/orbis-status
install -m 0755 "$BASE_DIR/orbis-mode" /usr/local/bin/orbis-mode

echo "[4/7] Configurando serviço runit..."
install -d -m 0755 /etc/sv/orbisd
install -m 0755 "$BASE_DIR/service/run" /etc/sv/orbisd/run
mkdir -p /var/service
ln -sfn /etc/sv/orbisd /var/service/orbisd

echo "[5/7] Habilitando SSH..."
if [ -d /etc/sv/ssh ]; then
  ln -sfn /etc/sv/ssh /var/service/ssh
elif [ -d /etc/sv/sshd ]; then
  ln -sfn /etc/sv/sshd /var/service/sshd
fi

echo "[6/7] Reduzindo escritas desnecessárias no cartão..."
if ! grep -q '^tmpfs[[:space:]]\+/tmp' /etc/fstab; then
  printf '%s\n' 'tmpfs /tmp tmpfs defaults,noatime,nosuid,nodev,mode=1777,size=128M 0 0' >> /etc/fstab
fi

# Evita depender de swap em cartão flash; não apaga arquivos existentes.
swapoff -a 2>/dev/null || true
if [ -f /etc/fstab ]; then
  cp -a /etc/fstab /etc/fstab.orbis-backup
  sed -i '/^[^#].*[[:space:]]swap[[:space:]]/ s/^/# Orbis disabled: /' /etc/fstab
fi

echo "[7/7] Iniciando serviço..."
sv up orbisd 2>/dev/null || true
sleep 2

cat <<'EOF'

OrbisOS Core instalado.

Teste agora:
  orbis-status
  sudo sv status orbisd

Mantenha o desktop nesta primeira inicialização.
Quando confirmar que tudo funciona:
  sudo orbis-mode terminal
  sudo reboot

Para restaurar:
  sudo orbis-mode desktop
  sudo reboot
EOF
