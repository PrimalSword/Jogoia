#!/bin/sh
set -eu

SRC_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
INSTALL_DIR=/usr/local/lib/orbis-trade
BIN=/usr/local/bin/orbis-trade
LAB_BIN=/usr/local/bin/orbis-trade-lab
WEB_BIN=/usr/local/bin/orbis-trade-web
DATA_DIR=/var/lib/orbis/trade
PID_FILE=/run/orbis-trade-web.pid
LOG_FILE=/var/log/orbis-trade-web.log

python3 -m py_compile "$SRC_DIR/orbis_trade.py" "$SRC_DIR/orbis_trade_web.py" "$SRC_DIR/orbis_trade_lab.py"
mkdir -p "$INSTALL_DIR" "$DATA_DIR" /run
cp "$SRC_DIR/orbis_trade.py" "$INSTALL_DIR/orbis_trade.py"
cp "$SRC_DIR/orbis_trade_web.py" "$INSTALL_DIR/orbis_trade_web.py"
cp "$SRC_DIR/orbis_trade_lab.py" "$INSTALL_DIR/orbis_trade_lab.py"
chmod 0755 "$INSTALL_DIR/orbis_trade.py" "$INSTALL_DIR/orbis_trade_web.py" "$INSTALL_DIR/orbis_trade_lab.py"

cat > "$BIN" <<'EOF'
#!/bin/sh
exec python3 /usr/local/lib/orbis-trade/orbis_trade.py "$@"
EOF
chmod 0755 "$BIN"

cat > "$LAB_BIN" <<'EOF'
#!/bin/sh
exec python3 /usr/local/lib/orbis-trade/orbis_trade_lab.py "$@"
EOF
chmod 0755 "$LAB_BIN"

cat > "$WEB_BIN" <<'EOF'
#!/bin/sh
PID_FILE=/run/orbis-trade-web.pid
LOG_FILE=/var/log/orbis-trade-web.log
case "${1:-start}" in
  start)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "Orbis Trade Web já está rodando."
      exit 0
    fi
    nohup python3 /usr/local/lib/orbis-trade/orbis_trade_web.py >>"$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2
    ;;
  stop)
    if [ -f "$PID_FILE" ]; then
      kill "$(cat "$PID_FILE")" 2>/dev/null || true
      rm -f "$PID_FILE"
    fi
    exit 0
    ;;
  restart)
    "$0" stop
    "$0" start
    ;;
  status)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "rodando pid $(cat "$PID_FILE")"
      exit 0
    fi
    echo "parado"
    exit 1
    ;;
  *) echo "uso: orbis-trade-web {start|stop|restart|status}" >&2; exit 2 ;;
esac
wget -q -T 5 -O - http://127.0.0.1:8090/health | grep -qx ok
EOF
chmod 0755 "$WEB_BIN"

if [ -d /etc/local.d ]; then
  cat > /etc/local.d/orbis-trade.start <<'EOF'
#!/bin/sh
/usr/local/bin/orbis-trade-web start >/dev/null 2>&1 || true
EOF
  chmod 0755 /etc/local.d/orbis-trade.start
  rc-update add local default >/dev/null 2>&1 || true
fi

"$WEB_BIN" restart

printf '%s\n' "Orbis Trade instalado."
printf '%s\n' "CLI principal: orbis-trade status"
printf '%s\n' "Quant Lab: orbis-trade-lab --help"
printf '%s\n' "Painel: http://100.87.144.114:8090"
printf '%s\n' "Modo atual: análise, otimização, Monte Carlo, replay e paper trading; nenhuma ordem real é enviada."
