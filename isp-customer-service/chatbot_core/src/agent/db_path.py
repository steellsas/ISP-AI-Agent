"""Where the SQLite world lives — one answer for the agent, the API, the eval and the tests.

Iki 5 bangos vieta buvo įrašyta keturiose vietose atskirai (`agent/tools.py`, `app/admin.py`,
`app/archive.py`, `tests/conftest.py`, plus `scripts/*`), ir visos rodė į TĄ PATĮ failą. Kaina
buvo matoma kasdien: `pytest` kiekvieną sesiją tą failą TRINA ir atkuria iš sėklų, tad kol
paleistas serveris (ar eval'as), testai lūžta su `PermissionError [WinError 32]` — Windows
neleidžia ištrinti failo, kurį kas nors laiko atsidaręs.

Todėl kelią dabar sako VIENA vieta, ir jį galima perrašyti aplinkos kintamuoju:

    DATABASE_PATH=database/isp_database.test.db   # santykinis — nuo projekto šaknies
    DATABASE_PATH=D:/tmp/demo.db                  # arba absoliutus

Kintamojo vardas ne naujas: `shared/src/utils/config.py` jį skaitė nuo pat pradių, tik agento
pusė to nepaisydavo. Numatytoji reikšmė nepakito, tad demo ir dashboard'as dirba su ta pačia
`database/isp_database.db` kaip anksčiau — savas failas atsiranda tik ten, kur jo prašoma:
testuose ir eval'e.
"""

from __future__ import annotations

import os
from pathlib import Path

# .../isp-customer-service/chatbot_core/src/agent/db_path.py -> isp-customer-service
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_DB = PROJECT_ROOT / "database" / "isp_database.db"


def database_path() -> Path:
    """Kur šiam procesui gyvena SQLite bazė.

    Skaitoma kiekvieno kvietimo metu, ne importo: eval'as kintamąjį nustato pats prieš pirmą
    scenarijų, o testai — `conftest` viršuje.
    """
    env = (os.getenv("DATABASE_PATH") or "").strip()
    if not env:
        return DEFAULT_DB
    path = Path(env)
    return path if path.is_absolute() else PROJECT_ROOT / path
