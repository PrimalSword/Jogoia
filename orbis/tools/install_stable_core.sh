#!/bin/sh
set -eu

REPO=/opt/orbis-src
SOURCE="$REPO/orbis/core/orbis_core.py"
TARGET=/usr/local/lib/orbis/orbis_core.py
BACKUP="${TARGET}.before-stable-install"
TMP="$(mktemp /tmp/orbis-core.XXXXXX.py)"
trap 'rm -f "$TMP"' EXIT

if [ ! -f "$SOURCE" ]; then
    echo "Fonte não encontrada: $SOURCE" >&2
    exit 1
fi

# O painel estável usa sequências JavaScript escapadas. A versão defeituosa
# contém quebras de linha reais dentro das strings do terminal.
python3 - "$SOURCE" "$TMP" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
start = source.find("function terminalHistory()")
end = source.find("\nrefresh();setInterval(refresh,10000);", start)
if start < 0 or end < 0:
    raise SystemExit("Bloco do terminal não localizado; nada foi alterado.")

block = source[start:end]
block = block.replace("'Executando…\\n\\n$ '+command+'\\n'", "'Executando…\\\\n\\\\n$ '+command+'\\\\n'")
block = block.replace("'$ '+command+'\\n\\n'+(data.output||data.error||'')+'\\n\\n[shell '", "'$ '+command+'\\\\n\\\\n'+(data.output||data.error||'')+'\\\\n\\\\n[shell '")
patched = source[:start] + block + source[end:]

if "subprocess.run([TERMINAL_SHELL, \"-lc\", command]" not in patched:
    raise SystemExit("Executor Alpine /bin/sh não encontrado; nada foi instalado.")

Path(sys.argv[2]).write_text(patched, encoding="utf-8")
PY

python3 -m py_compile "$TMP"

python3 - "$TMP" <<'PY'
from importlib.machinery import SourceFileLoader
import sys

module = SourceFileLoader("orbis_candidate", sys.argv[1]).load_module()
page = module.dashboard_shell()
if "refresh();setInterval(refresh,10000);" not in page:
    raise SystemExit("Telemetria não localizada no HTML candidato.")
if "Executando…\\n\\n$ " not in page:
    raise SystemExit("Escapes do terminal não foram preservados.")
if "Executando…\n\n$ " in page:
    raise SystemExit("JavaScript inválido detectado; Core atual preservado.")
PY

cp "$TARGET" "$BACKUP"
cp "$TMP" "$TARGET"
chmod 0755 "$TARGET"
/usr/local/bin/orbis-web --restart
sleep 4

if wget -q -T 5 -O - http://127.0.0.1:8080/health | grep -qx ok; then
    echo "SUCESSO: Core estável instalado; painel e terminal Alpine preservados."
else
    echo "Falha no health check; restaurando Core anterior..." >&2
    cp "$BACKUP" "$TARGET"
    /usr/local/bin/orbis-web --restart
    exit 1
fi
