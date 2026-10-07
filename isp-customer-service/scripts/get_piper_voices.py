"""Atsisiunčia lietuviškus Piper balsus (Reginutė, Ingutė) į `models/tts/piper/`.

    uv run python scripts/get_piper_voices.py            # abu balsai
    uv run python scripts/get_piper_voices.py ingute     # tik vienas

Balsai ir jų fonemizatorius git'e nelaikomi: `.onnx` po 63 MB, o fonemizatoriaus kodas yra
GPL-3.0 (kaip ir piper1-gpl), todėl jis guli šalia modelio, ne mūsų `src/`. Kiekvienas failas
paimamas iš UŽFIKSUOTOS Hugging Face versijos ir patikrinamas SHA256 — tas pats balsas šiandien
ir po metų; pakeistas failas atsisiųsti nepavyks.

Kilmė ir licencijos:
  * Reginutė  `lt_LT-reginute1-medium` — CC-BY-4.0 (VU LIEPA garsynas), Robertas Tarasevičius & Claude
  * Ingutė    `lt_LT-ingute-medium`    — NewGenLTU OpenRAIL-D 1.0 (`LICENSE-VOICE`), išaugusi iš Reginutės
  * fonemizatorius, skaičių plėtiklis, sintezės receptas — GPL-3.0-only
Balsas sintetinis: klientui pasakom, kad kalba DI (ES DI aktas, 50 str.).
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "models" / "tts" / "piper"

# Bendri abiem balsams (identiški abiejose saugyklose — sutikrinta SHA256).
SHARED_REPO = ("RobertasTa/lt_LT-reginute1-medium", "eb72c5b84303f41197983b465a71bccea80b1057")
SHARED = {
    "phonemize_lithuanian.py": "fe67149a297435ad7d4283bdc230efce745896eff2c1688489967b59584e413f",
    "skaiciu_pletiklis.py": "7fbade35ddccaadbb3fdcc5817bbff72c011bbfcf54df1a9a0d5ce999ef3dd59",
    "synth_reginute.py": "d36c102fae095bea2997ac5bccb8a98a6734a2f32c3fa3ec8e593afa663a6e05",
    "lt_kirciai.tsv": "193a67c77e20c1d15a2b6c8cddd7b632ed5bce6a4985cca2008b5c48daf57f84",
    "lt_kreipiniai.tsv": "02d87d9262596beea94f2d0ca5f6b88bb7f12ccdda6499c058dbbfbc1f13ec89",
    "lt_raides.tsv": "e3b81bb7d64177236203e3c8304e3c92cd5e414da3c5a513b265a3258e2e4db1",
    "zodziai_trumpi.txt": "d31f30d1cd088953e20fee14028945ac877cccf4e939936a70070d0ea38ea4f3",
}

VOICES = {
    "reginute": (
        ("RobertasTa/lt_LT-reginute1-medium", "eb72c5b84303f41197983b465a71bccea80b1057"),
        {
            "lt_LT-reginute1-medium.onnx": "0417c4ef351686ec0b0e7bf63426aefc72faea4a7693cfcb2f01ea8f6ee986ee",
            "lt_LT-reginute1-medium.onnx.json": "cce5719a544d416fb9c1992013a568215caf4d236117f58b459ce780d049bba9",
            "MODEL_CARD": "eafd8b5aaacfee9d3710e0211295bf4aeaf7cd3bc9c4310bd139bb0503c14b7c",
        },
    ),
    "ingute": (
        ("RobertasTa/lt_LT-ingute-medium", "854c181f017744aaae76462608f07c9352d2ee0d"),
        {
            "lt_LT-ingute-medium.onnx": "31bdf1df5339e7da0e0f8c8e847e0f9e720bb732c0ffc7fb3d81970844b441d8",
            "lt_LT-ingute-medium.onnx.json": "a61a4703f03385034c913b053c0242f723fd3d89446c711234b8fe21ec01dfc2",
            "MODEL_CARD": "b293ca30c3982c6f103d8a6e7af6730250fb44f55d0a4b2b6dc137d7f5174ede",
            "LICENSE-VOICE": "a359105275a97d1adf721cb4b49e249407742a268e381ecfc7181f59d9419075",
        },
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _fetch(repo: tuple[str, str], name: str, expected: str, dest: Path) -> None:
    target = dest / name
    if target.is_file() and _sha256(target) == expected:
        print(f"  ✓ {name} (jau yra)")
        return
    repo_id, revision = repo
    url = f"https://huggingface.co/{repo_id}/resolve/{revision}/{name}"
    tmp = target.with_suffix(target.suffix + ".part")
    print(f"  ↓ {name}")
    urllib.request.urlretrieve(url, tmp)
    actual = _sha256(tmp)
    if actual != expected:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"SHA256 nesutampa: {name}\n  laukta {expected}\n  gauta  {actual}")
    tmp.replace(target)


def main(names: list[str]) -> None:
    unknown = [n for n in names if n not in VOICES]
    if unknown:
        raise SystemExit(f"Nežinomas balsas: {', '.join(unknown)} (yra: {', '.join(VOICES)})")
    ROOT.mkdir(parents=True, exist_ok=True)
    print(f"Fonemizatorius → {ROOT}")
    for name, sha in SHARED.items():
        _fetch(SHARED_REPO, name, sha, ROOT)
    for voice in names or list(VOICES):
        repo, files = VOICES[voice]
        print(f"Balsas {voice} → {ROOT / voice}")
        (ROOT / voice).mkdir(exist_ok=True)
        for name, sha in files.items():
            _fetch(repo, name, sha, ROOT / voice)
    print("Paruošta. Įjungti: TTS_ENGINE=piper, TTS_PIPER_VOICE=reginute|ingute")


if __name__ == "__main__":
    main(sys.argv[1:])
