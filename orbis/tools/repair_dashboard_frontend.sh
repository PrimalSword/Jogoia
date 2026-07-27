#!/bin/sh
set -eu

INSTALLED="/usr/local/lib/orbis/orbis_core.py"
BACKUP="${INSTALLED}.frontend-backup"
TMP="${INSTALLED}.frontend-tmp"

python3 - "$INSTALLED" "$TMP" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
text = source.read_text(encoding="utf-8")

old = """terminalOutput.textContent='Executando…\n\n$ '+command+'\n';try{{const raw=await admin('/api/terminal/exec',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{command,cwd}})}});const data=JSON.parse(raw);terminalOutput.textContent='$ '+command+'\n\n'+(data.output||data.error||'')+'\n\n[shell '+(data.shell||'?')+' · exit '+(data.exit_code??'?')+' · '+(data.duration_ms??'?')+' ms]';"""

new = """terminalOutput.textContent='Executando…\\n\\n$ '+command+'\\n';try{{const raw=await admin('/api/terminal/exec',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{command,cwd}})}});const data=JSON.parse(raw);terminalOutput.textContent='$ '+command+'\\n\\n'+(data.output||data.error||'')+'\\n\\n[shell '+(data.shell||'?')+' · exit '+(data.exit_code??'?')+' · '+(data.duration_ms??'?')+' ms]';"""

if old not in text:
    raise SystemExit("Trecho esperado do JavaScript não foi encontrado; nenhum arquivo foi alterado.")

target.write_text(text.replace(old, new, 1), encoding="utf-8")
PY

python3 -m py_compile "$TMP"
cp "$INSTALLED" "$BACKUP"
mv "$TMP" "$INSTALLED"
/usr/local/bin/orbis-web --restart
sleep 5

if wget -q -T 5 -O - http://127.0.0.1:8080/health | grep -qx "ok"; then
    echo "SUCESSO: frontend corrigido, repositório preservado e Core saudável."
    exit 0
fi

echo "FALHA: restaurando Core anterior..."
cp "$BACKUP" "$INSTALLED"
/usr/local/bin/orbis-web --restart
sleep 3
exit 1
