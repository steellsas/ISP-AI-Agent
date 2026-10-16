"""Ar Smart Turn supranta lietuvių kalbą? — bandymas ant įrašytų kliento ėjimų (DELSA A1.1).

Pipecat Smart Turn v3 (BSD-2, ONNX, garso modelis) pasako, ar žmogus BAIGĖ mintį. LT jo mokymo
sąraše nėra, todėl matuojame ant mūsų pačių įrašų `logs/sessions/*/turn_NN_user.wav`:

    baigė    — visas ėjimas, nukirptas ties kalbos pabaiga + 200 ms tylos  → turi sakyti „baigė"
    nebaigė  — tas pats ėjimas, nukirptas per pauzę VIDURYJE (≥ 1 s kalbos prieš, ≥ 0,7 s po)
               → turi sakyti „nebaigė"

Svarbiausia klaida — „baigė" ant nebaigto (agentas pertrauktų klientą).
Pastaba: pauzė viduryje kartais yra sakinio riba („Taip. Dega lemputė.") — ten „baigė" nėra
klaida; tokie atvejai matomi su --show.

Modelis (vieną kartą, į `models/turn/`, kuris į git nepatenka):

    curl -L -o models/turn/smart-turn-v3.2-cpu.onnx \
      https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/f766f81d3cfdf7737ac64aad813d91bbfd56bf93/smart-turn-v3.2-cpu.onnx

Paleidimas:

    uv run python scripts/smart_turn_eval.py                    # visi įrašai
    uv run python scripts/smart_turn_eval.py --limit 100 --show 15
    uv run python scripts/smart_turn_eval.py --threshold 0.7
"""

from __future__ import annotations

import argparse
import glob
import statistics
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "sessions"
MODEL = ROOT / "models" / "turn" / "smart-turn-v3.2-cpu.onnx"

SR = 16000
FRAME = 320  # 20 ms
SPEECH_DB = 45.0  # int16 RMS lygis dB; tyla po triukšmo slopinimo ~0–30, kalba ~55–75
TAIL_S = 0.2  # tyla po kalbos, kurią modelis mato (kaip Pipecat: VAD stop ~200 ms)
MIN_PAUSE_S = 0.15
BEFORE_S = 1.0
AFTER_S = 0.7


def load(path: str) -> np.ndarray:
    with wave.open(path) as w:
        if w.getframerate() != SR or w.getnchannels() != 1:
            return np.zeros(0, dtype=np.float32)
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return x.astype(np.float32)


def speech_frames(x: np.ndarray) -> np.ndarray:
    n = len(x) // FRAME
    fr = x[: n * FRAME].reshape(n, FRAME)
    db = 20 * np.log10(np.sqrt((fr**2).mean(axis=1)) + 1e-9)
    return db > SPEECH_DB


def samples(x: np.ndarray) -> tuple[np.ndarray | None, list[tuple[np.ndarray, float]]]:
    """Grąžina (baigtas ėjimas, [(nukirpimas per vidurinę pauzę, pauzės ilgis s)])."""
    sp = speech_frames(x)
    idx = np.flatnonzero(sp)
    if len(idx) < 10:  # < 0,2 s kalbos
        return None, []
    end = idx[-1] + 1
    tail = int(TAIL_S * SR / FRAME)
    complete = x[: (end + tail) * FRAME]

    cuts = []
    pause_min = int(MIN_PAUSE_S * SR / FRAME)
    before = int(BEFORE_S * SR / FRAME)
    after = int(AFTER_S * SR / FRAME)
    i, start = idx[0], idx[0]
    while i < end:
        if not sp[i]:
            j = i
            while j < end and not sp[j]:
                j += 1
            if j - i >= pause_min and i - start >= before and end - j >= after:
                # modelis mato tą patį, ką matytų gyvai: kalba iki pauzės + 200 ms tylos
                cuts.append((x[: min(i + tail, j) * FRAME], (j - i) * FRAME / SR))
            i = j
        else:
            i += 1
    return complete, cuts


class SmartTurn:
    def __init__(self, path: Path) -> None:
        import onnxruntime as ort
        from transformers import WhisperFeatureExtractor

        opts = ort.SessionOptions()
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(path), sess_options=opts)
        self.fe = WhisperFeatureExtractor(chunk_length=8)

    def prob(self, audio: np.ndarray) -> float:
        a = audio / 32768.0
        a = a[-8 * SR :]  # paskutinės 8 s
        feats = self.fe(
            a,
            sampling_rate=SR,
            return_tensors="np",
            padding="max_length",
            max_length=8 * SR,
            truncation=True,
            do_normalize=True,
        ).input_features
        out = self.session.run(None, {"input_features": feats.astype(np.float32)})
        return float(np.asarray(out[0]).reshape(-1)[0])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0, help="tik N įrašų")
    ap.add_argument("--show", type=int, default=0, help="parodyti N klaidų kiekvienos rūšies")
    args = ap.parse_args()

    if not MODEL.exists():
        print(f"Nėra modelio {MODEL} — žr. docstring.")
        return 1
    model = SmartTurn(MODEL)
    files = sorted(glob.glob(str(LOGS / "*" / "turn_*_user.wav")))
    if args.limit:
        files = files[-args.limit :]

    complete_p: list[tuple[float, str]] = []
    cut_p: list[tuple[float, str, float]] = []
    per_turn: list[list[tuple[float, float]]] = []  # kiekvienam ėjimui: (p, pauzės ilgis)
    times: list[float] = []
    skipped = 0
    for f in files:
        x = load(f)
        complete, cuts = samples(x)
        if complete is None:
            skipped += 1
            continue
        name = str(Path(f).relative_to(LOGS))
        t0 = time.perf_counter()
        complete_p.append((model.prob(complete), name))
        times.append((time.perf_counter() - t0) * 1000)
        pauses = []
        for c, pause in cuts:
            p = model.prob(c)
            cut_p.append((p, name, len(c) / SR))
            pauses.append((p, pause))
        per_turn.append(pauses)

    thr = args.threshold
    ok_complete = sum(p > thr for p, _ in complete_p)
    ok_cut = sum(p <= thr for p, _, _ in cut_p)
    n_c, n_i = len(complete_p), len(cut_p)
    print(f"Įrašai: {len(files)} (praleista be kalbos: {skipped}); slenkstis {thr}")
    print(f"Inferencija CPU: mediana {statistics.median(times):.0f} ms, max {max(times):.0f} ms")
    print()
    print(f"{'atvejis':<34}{'kiek':>6}{'teisinga':>10}")
    print(f"{'baigė (visas ėjimas)':<34}{n_c:>6}{100 * ok_complete / max(n_c, 1):>9.1f}%")
    print(f"{'nebaigė (pauzė viduryje)':<34}{n_i:>6}{100 * ok_cut / max(n_i, 1):>9.1f}%")
    total = n_c + n_i
    print(f"{'iš viso':<34}{total:>6}{100 * (ok_complete + ok_cut) / max(total, 1):>9.1f}%")
    print()
    print(f"Klaidingas „baigė“ (pertrauktų): {100 * (n_i - ok_cut) / max(n_i, 1):.1f}% nebaigtų")
    print(
        f"Klaidingas „nebaigė“ (lauktų ilgiau): {100 * (n_c - ok_complete) / max(n_c, 1):.1f}% baigtų"
    )

    print("\nSlenksčio įtaka:")
    print(f"  {'slenkstis':>9} {'baigė ✓':>8} {'nebaigė ✓':>10}")
    for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        a = sum(p > t for p, _ in complete_p) / max(n_c, 1)
        b = sum(p <= t for p, _, _ in cut_p) / max(n_i, 1)
        print(f"  {t:>9} {100 * a:>7.1f}% {100 * b:>9.1f}%")

    # Taisyklė „kirpti po W ms tylos, jei modelis sako baigė (p > t)“ — kiek ėjimų pertrauktume?
    # Ėjimas pertraukiamas, jei jame yra vidurinė pauzė ≥ W, kurioje p > t.
    print("\nTaisyklės simuliacija: kirpti po W ms tylos, kai p > t (dabar fiksuota 900 ms):")
    print(f"  {'W ms':>5} {'t':>5} {'pertraukti ėjimai':>18}")
    for w in (200, 300, 500):
        for t in (0.0, 0.5, 0.7, 0.9):
            hit = sum(any(p > t and pause >= w / 1000 for p, pause in turn) for turn in per_turn)
            print(f"  {w:>5} {t:>5} {100 * hit / max(len(per_turn), 1):>17.1f}%")
    long_pauses = [pause for turn in per_turn for _, pause in turn]
    for w in (200, 300, 500, 900):
        n = sum(pause >= w / 1000 for pause in long_pauses)
        print(f"  vidurinių pauzių ≥ {w} ms: {n}")

    if args.show:
        print("\nBaigti, bet modelis sako „nebaigė“:")
        for p, name in sorted(complete_p)[: args.show]:
            if p <= thr:
                print(f"  {p:.2f}  {name}")
        print("\nNebaigti (nukirpta per pauzę), bet modelis sako „baigė“:")
        for p, name, sec in sorted(cut_p, reverse=True)[: args.show]:
            if p > thr:
                print(f"  {p:.2f}  {name}  (nukirpta ties {sec:.1f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
