#!/bin/sh
set -eu

SRC_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
INSTALL_DIR=/usr/local/lib/orbis-trade
BIN=/usr/local/bin/orbis-trade
DATA_DIR=/var/lib/orbis/trade

python3 -m py_compile "$SRC_DIR/orbis_trade.py"
mkdir -p "$INSTALL_DIR" "$DATA_DIR"
cp "$SRC_DIR/orbis_trade.py" "$INSTALL_DIR/orbis_trade.py"
chmod 0755 "$INSTALL_DIR/orbis_trade.py"

cat > "$BIN" <<'EOF'
#!/bin/sh
exec python3 /usr/local/lib/orbis-trade/orbis_trade.py "$@"
EOF
chmod 0755 "$BIN"

printf '%s\n' "Orbis Trade instalado."
printf '%s\n' "Teste: orbis-trade status"
printf '%s\n' "Modo atual: análise, replay e backtest; nenhuma ordem real é enviada."
