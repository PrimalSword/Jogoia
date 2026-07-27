#!/bin/sh
set -eu

INSTALLED="/usr/local/lib/orbis/orbis_core.py"
BACKUP="${INSTALLED}.frontend-backup"
TMP="${INSTALLED}.frontend-tmp.py"

cleanup() {
    rm -f "$TMP"
}
trap cleanup EXIT

python3 - "$INSTALLED" "$TMP" <<'PY'
from pathlib import Path
import re
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
text = source.read_text(encoding="utf-8")

replacement = r"""async function executeTerminal(){{const command=terminalCommand.value.trim();const cwd=terminalCwd.value.trim()||'/opt/orbis-src';if(!command){{terminalOutput.textContent='Digite um comando.';return;}}saveTerminalCommand(command);terminalOutput.textContent='Executando…\\n\\n$ '+command+'\\n';try{{const raw=await admin('/api/terminal/exec',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{command,cwd}})}});const data=JSON.parse(raw);terminalOutput.textContent='$ '+command+'\\n\\n'+(data.output||data.error||'')+'\\n\\n[shell '+(data.shell||'?')+' · exit '+(data.exit_code??'?')+' · '+(data.duration_ms??'?')+' ms]';}}catch(e){{terminalOutput.textContent='Falha: '+e.message;}}}}"""

pattern = re.compile(
    r"async function executeTerminal\(\)\{\{.*?\}\}\s*(?=refresh\(\);setInterval)",
    re.DOTALL,
)

# Use uma função de substituição: re.sub interpreta barras invertidas em strings
# de reposição e transformava \\n novamente em quebra de linha real.
patched, count = pattern.subn(lambda _match: replacement, text, count=1)
if count != 1:
    raise SystemExit(
        "Função executeTerminal não foi localizada de forma segura; nenhum arquivo foi alterado."
    )

target.write_text(patched, encoding="utf-8")
PY

python3 -m py_compile "$TMP"

# Valida o HTML realmente entregue ao navegador antes de substituir o Core ativo.
python3 - "$TMP" <<'PY'
from importlib.machinery import SourceFileLoader
import sys
import types

path = sys.argv[1]
module = types.ModuleType("orbis_core_candidate")
module.__file__ = path
SourceFileLoader(module.__name__, path).exec_module(module)
page = module.dashboard_shell()

expected = "Executando…\\n\\n$ "
broken = "Executando…\n\n$ "
if expected not in page or broken in page:
    raise SystemExit("Validação do JavaScript falhou; Core ativo preservado.")

# A telemetria depende deste trecho continuar presente no mesmo script.
if "refresh();setInterval(refresh,10000);" not in page:
    raise SystemExit("Validação da telemetria falhou; Core ativo preservado.")
PY

cp "$INSTALLED" "$BACKUP"
cp "$TMP" "$INSTALLED"
/usr/local/bin/orbis-web --restart
sleep 5

if wget -q -T 5 -O - http://127.0.0.1:8080/health | grep -qx "ok"; then
    echo "SUCESSO: frontend corrigido e Core saudável."
    exit 0
fi

echo "FALHA: restaurando Core anterior..."
cp "$BACKUP" "$INSTALLED"
/usr/local/bin/orbis-web --restart
sleep 3
exit 1
