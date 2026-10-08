"""Vercel serverless entrypoint: reusa o Flask de server/app.py sem alterá-lo.

No Vercel o disco é somente leitura (exceto /tmp), então os JSONs de
contas vão para /tmp/prf-dados (efêmero: zera entre deploys/instâncias).
Localmente nada muda: `python server/app.py` continua usando server/dados/.
"""
import importlib.util
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if os.environ.get("VERCEL"):
    os.environ.setdefault("PRF_DATA_DIR", "/tmp/prf-dados")

_spec = importlib.util.spec_from_file_location(
    "prf_server_app", os.path.join(BASE, "server", "app.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

app = _mod.app
