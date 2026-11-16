"""Triukšmo stendas (I-4/I-5, T2): kiek fonas gadina tai, ką agentas išgirsta telefonu.

Matuojame tuo pačiu keliu kaip skambutis telefono režimu, tik be skambinimo:

    švarus kliento ėjimas (16 kHz, `logs/sessions/*/turn_NN_user.wav`)
      → 8 kHz → + fonas (tikras, iš telefono režimo įrašų `call_caller_raw.wav`)
      → G.711 μ-law → [filtras] → Silero VAD 8 kHz (kaip skambutyje) → atkarpos
      → [filtras prieš ASR] → Groq Whisper → `is_asr_noise`

Kas lyginama:
    CER     — simbolių klaidos prieš švaraus ėjimo tekstą (16 kHz, be fono) — „atskaita"
    prarasta — ėjimas, iš kurio neliko nieko (VAD neišgirdo arba filtras išmetė)
    fantomai — vien fono atkarpos (be kalbos), iš kurių ASR padarė „kliento žodžius"

Fono lygiai: `as_is` — kaip įrašyta (TV per ~3 m), ir SNR 10/5/0 dB — kalba vis
garsiau užgožiama. Atskaita ir ASR atsakymai kešuojami `logs/bench/`, todėl antras
paleidimas su tais pačiais ėjimais nemoka nieko; atskaitą galima pataisyti ranka
(`logs/bench/reference.json`) — tada CER skaičiuojamas prieš teisingą tekstą.

Variantai (`--variant`, galima kelis): `none` — kaip dabar skambutyje; `gain` —
atkarpa pakeliama iki −20 dBFS prieš ASR. Nauji filtrai (RNNoise, VAD nustatymai)
pridedami į `VARIANTS`.

Paleidimas (raktai iš `.env` įkeliami proceso viduje, niekur nespausdinami):

    uv run python scripts/noise_bench.py --limit 24 --snr as_is 10 0
    uv run python scripts/noise_bench.py --variant none gain --show 10
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import re
import sys
import time
import unicodedata
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "sessions"
BENCH = ROOT / "logs" / "bench"

RATE = 8000
FRAME = 160  # 20 ms at 8 kHz
PRE_ROLL_S = 1.0  # SegmentedSTTService keeps 1 s before VAD start
TRAIL_S = 0.5  # …and pads 0.5 s of silence after VAD stop
LEAD_S = 1.5  # background before and after the turn, so VAD hears the room first
MARGIN_S = 0.4  # kept away from caller speech when cutting background
AGENT_MARGIN_S = 0.8  # …and from the agent (its echo)


# --- pure helpers (tested) ------------------------------------------------------------


def normalize(text: str) -> str:
    """Lower case, no punctuation, single spaces — what CER is counted on."""
    t = unicodedata.normalize("NFC", text or "").lower()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return " ".join(t.split())


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


def dbfs(pcm: np.ndarray) -> float:
    x = pcm.astype(np.float64)
    rms = float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
    return 20 * np.log10(max(rms, 1e-9) / 32768)


def scale_to(pcm: np.ndarray, target_dbfs: float) -> np.ndarray:
    gain = 10 ** ((target_dbfs - dbfs(pcm)) / 20)
    return np.clip(pcm.astype(np.float64) * gain, -32768, 32767).astype(np.int16)


def mix(speech: np.ndarray, noise: np.ndarray, snr_db: float | None) -> np.ndarray:
    """`speech` placed over `noise` (same length or longer); `snr_db=None` keeps the
    background as recorded, a number scales it to that speech-to-noise ratio."""
    noise = noise[: len(speech)].astype(np.float64)
    if snr_db is not None:
        active = speech[np.abs(speech) > 0]
        s_rms = np.sqrt(np.mean(active.astype(np.float64) ** 2)) if len(active) else 0.0
        n_rms = np.sqrt(np.mean(noise**2)) or 1.0
        noise = noise * (s_rms / n_rms) / (10 ** (snr_db / 20))
    return np.clip(speech.astype(np.float64) + noise, -32768, 32767).astype(np.int16)


def background_spans(
    timeline: list[dict], total_s: float, asr_scale: float = 1.0
) -> list[tuple[float, float]]:
    """Stretches of a raw call with neither the caller (VAD/ASR) nor the agent in them.
    `asr_scale=2` for calls before the 8 kHz fix: their ASR marks carry half the length."""
    busy: list[tuple[float, float]] = []
    opened: dict[str, float] = {}
    for x in timeline:
        k, t = x["kind"], x["t"]
        if k in ("vad_start", "agent_start"):
            opened[k] = t
        elif k == "vad_stop" and "vad_start" in opened:
            busy.append((opened.pop("vad_start") - MARGIN_S, t + MARGIN_S))
        elif k == "agent_stop" and "agent_start" in opened:
            busy.append((opened.pop("agent_start") - MARGIN_S, t + AGENT_MARGIN_S))
        elif k == "asr" and "start" in x:
            secs = (x["end"] - x["start"]) * asr_scale
            busy.append((x["end"] - secs - MARGIN_S, x["end"] + MARGIN_S))
    for k, t in opened.items():
        busy.append((t - MARGIN_S, total_s))
    # The greeting starts before the track: a first agent_stop with no start before it.
    agent = [x for x in timeline if x["kind"] in ("agent_start", "agent_stop")]
    if agent and agent[0]["kind"] == "agent_stop":
        busy.append((0.0, agent[0]["t"] + AGENT_MARGIN_S))
    busy.sort()
    free, cursor = [], 0.0
    for a, b in busy:
        if a > cursor:
            free.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < total_s:
        free.append((cursor, total_s))
    return [(a, b) for a, b in free if b - a >= 1.0]


def wav_bytes(pcm: np.ndarray, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


# --- variants -----------------------------------------------------------------------------


@dataclass
class Variant:
    """A filter under test: before VAD (the whole line) and before ASR (one segment)."""

    name: str
    pre_vad: Callable[[np.ndarray], np.ndarray] = lambda x: x
    pre_asr: Callable[[np.ndarray], np.ndarray] = lambda x: x
    vad_params: dict = field(default_factory=lambda: {"stop_secs": 0.2})
    whole_turn: bool = False  # one ASR call for the turn, from the first VAD start to the last stop


def _gain(seg: np.ndarray) -> np.ndarray:
    return scale_to(seg, -20.0) if dbfs(seg) < -20.0 else seg


def _vad(**params) -> dict:
    return {"stop_secs": 0.2, **params}


VARIANTS = {
    "none": Variant("none"),
    "gain": Variant("gain", pre_asr=_gain),
    # VAD's pause before a segment ends: 0.2 s splits a turn into pieces at 8 kHz,
    # and Whisper hears each piece without the rest of the sentence.
    "stop05": Variant("stop05", vad_params={"stop_secs": 0.5}),
    "stop08": Variant("stop08", vad_params={"stop_secs": 0.8}),
    # B: VAD stays at 0.2 s for turn-taking; the turn goes to ASR once, whole.
    "turn": Variant("turn", whole_turn=True),
    # On top of the whole turn (the call since 77dc9f4): VAD made deafer to a far room.
    # min_volume is BS.1770 loudness mapped -110..-10 LUFS → 0..1: 0.6 (Pipecat's
    # default) ≈ -50 LUFS, 0.7 ≈ -40, 0.75 ≈ -35; a caller into the phone is ~-25..-30,
    # the TV across the room ~-45 (2026-11-16).
    "vol07": Variant("vol07", vad_params=_vad(min_volume=0.7), whole_turn=True),
    "vol075": Variant("vol075", vad_params=_vad(min_volume=0.75), whole_turn=True),
    "conf085": Variant("conf085", vad_params=_vad(confidence=0.85), whole_turn=True),
    "start04": Variant("start04", vad_params=_vad(start_secs=0.4), whole_turn=True),
}

# Calls made to record the room alone (TV, people talking, no caller): every second the
# agent is silent is background — including what the call's ASR took for the caller.
BACKGROUND_ONLY = ("20261116-081020-227382-0002",)


# --- data -----------------------------------------------------------------------------------


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16), w.getframerate()


def phone_calls() -> list[Path]:
    """Calls recorded in phone mode with the 8 kHz fix (the raw track is labelled right
    in every phone call; the turn files of the calls before the fix are not)."""
    out = []
    for tl in sorted(LOGS.glob("*/call_timeline.jsonl")):
        first = _lines(tl)[0]
        if first.get("line") == "phone" and first.get("rate") == RATE:
            out.append(tl.parent)
    return out


def split_at_zeros(pcm: np.ndarray, rate: int = RATE, min_s: float = 1.0) -> list[np.ndarray]:
    """Pieces between runs of exact digital silence (≥ 0.1 s). The browser sends nothing
    in quiet stretches (Opus DTX) and the server fills them with zeros — a phone line
    carries the room there, so zeros are not a room to measure on."""
    frame = int(0.02 * rate)
    n = len(pcm) // frame
    if n == 0:
        return []
    silent = np.abs(pcm[: n * frame].reshape(n, frame)).max(axis=1) == 0
    pieces, start, i = [], 0, 0
    while i < n:
        if not silent[i]:
            i += 1
            continue
        j = i
        while j < n and silent[j]:
            j += 1
        if j - i >= 5:  # 0.1 s of zeros ends the piece before it
            if (i - start) * 0.02 >= min_s:
                pieces.append(pcm[start * frame : i * frame])
            start = j
        i = j
    if (n - start) * 0.02 >= min_s:
        pieces.append(pcm[start * frame : n * frame])
    return pieces


def background_bank(calls: list[Path], pure: bool) -> list[np.ndarray]:
    """The room: from calls made for it (`BACKGROUND_ONLY`, every agent-free second), or
    with `pure=False` also the gaps of ordinary calls (which may hold the caller)."""
    bank = []
    for d in calls:
        only_room = d.name in BACKGROUND_ONLY
        if pure and not only_room:
            continue
        pcm, rate = read_wav(d / "call_caller_raw.wav")
        timeline = _lines(d / "call_timeline.jsonl")
        if only_room:
            timeline = [x for x in timeline if x["kind"] in ("agent_start", "agent_stop")]
        scale = 2.0 if _code(d) == "f88d177" else 1.0  # recorded before the 8 kHz fix
        for a, b in background_spans(timeline, len(pcm) / rate, scale):
            bank += split_at_zeros(pcm[int(a * rate) : int(b * rate)], rate)
    return bank


def clean_turns(limit: int, seed: int) -> list[Path]:
    """Caller turns from browser calls (16 kHz, clean), 1–8 s long."""
    found = []
    for f in sorted(LOGS.glob("*/turn_*_user.wav")):
        if _is_phone(f.parent):
            continue
        try:
            with wave.open(str(f)) as w:
                secs = w.getnframes() / w.getframerate()
                if w.getframerate() != 16000 or not 1.0 <= secs <= 8.0:
                    continue
        except (wave.Error, EOFError):
            continue
        found.append(f)
    random.Random(seed).shuffle(found)
    return found[: limit * 2]  # spare: some turns have no speech once transcribed


def _lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def _is_phone(d: Path) -> bool:
    tl = d / "call_timeline.jsonl"
    return tl.exists() and _lines(tl)[0].get("line") == "phone"


def _code(d: Path) -> str:
    trace = d.parent / f"{d.name}.jsonl"
    if not trace.exists():
        return ""
    first = _lines(trace)[0]
    return first.get("versions", {}).get("code", "")


def to_8k(pcm16k: np.ndarray) -> np.ndarray:
    import soxr

    return soxr.resample(pcm16k, 16000, RATE, "HQ").astype(np.int16)


def line(pcm: np.ndarray) -> np.ndarray:
    sys.path.insert(0, str(ROOT / "chatbot_core" / "src"))
    from app.call_audio import ulaw_decode, ulaw_encode

    return ulaw_decode(ulaw_encode(pcm))


# --- the call's path ------------------------------------------------------------------------


class Hearing:
    """VAD at 8 kHz + the call's ASR, with a disk cache for every transcript."""

    def __init__(self) -> None:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT / "chatbot_core" / ".env")
        sys.path.insert(0, str(ROOT / "chatbot_core" / "src"))
        from adapters.asr.lt_text import is_asr_noise, normalize_lt_numbers
        from app.voice import _build_asr

        self._asr = _build_asr()
        self._noise = is_asr_noise
        self._numbers = normalize_lt_numbers
        BENCH.mkdir(parents=True, exist_ok=True)
        self._cache_path = BENCH / "asr_cache.json"
        self._cache = (
            json.loads(self._cache_path.read_text("utf-8")) if self._cache_path.exists() else {}
        )
        self.calls = 0

    def transcribe(self, wav: bytes) -> str:
        key = hashlib.sha1(wav).hexdigest()
        if key not in self._cache:
            for attempt in range(6):
                try:
                    self._cache[key] = self._asr.transcribe(wav, language="lt")
                    break
                except Exception as exc:  # rate limit: wait and retry
                    if attempt == 5 or "429" not in str(exc) and "rate" not in str(exc).lower():
                        raise
                    time.sleep(10 * (attempt + 1))
            self.calls += 1
            if self.calls % 20 == 0:
                self.save()
        return self._cache[key]

    def save(self) -> None:
        self._cache_path.write_text(json.dumps(self._cache, ensure_ascii=False), "utf-8")

    def heard(self, text: str) -> tuple[str, bool]:
        t = self._numbers(text or "")
        return t, (not t) or self._noise(t)

    def segments(self, pcm: np.ndarray, vad_params: dict) -> list[tuple[int, int]]:
        import asyncio

        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.audio.vad.vad_analyzer import VADParams, VADState

        async def run():
            vad = SileroVADAnalyzer(sample_rate=RATE, params=VADParams(**vad_params))
            vad.set_sample_rate(RATE)
            prev, start, out = VADState.QUIET, None, []
            raw = pcm.astype(np.int16).tobytes()
            step = FRAME * 2
            for i in range(0, len(raw) - step + 1, step):
                state = await vad.analyze_audio(raw[i : i + step])
                n = (i + step) // 2
                if state == VADState.SPEAKING and prev != VADState.SPEAKING and start is None:
                    start = n
                if state == VADState.QUIET and prev != VADState.QUIET and start is not None:
                    out.append((start, n))
                    start = None
                prev = state
            if start is not None:
                out.append((start, len(pcm)))
            return out

        return asyncio.run(run())

    def hear(self, pcm: np.ndarray, v: Variant) -> list[dict]:
        """What the call would hand the engine: one entry per VAD segment."""
        pcm = v.pre_vad(pcm)
        out = []
        spans = self.segments(pcm, v.vad_params)
        if v.whole_turn and spans:
            spans = [(spans[0][0], spans[-1][1])]
        for s, e in spans:
            seg = pcm[max(s - int(PRE_ROLL_S * RATE), 0) : e]
            seg = v.pre_asr(np.concatenate([seg, np.zeros(int(TRAIL_S * RATE), np.int16)]))
            text, dropped = self.heard(self.transcribe(wav_bytes(seg)))
            out.append({"t": round(s / RATE, 2), "text": text, "dropped": dropped})
        return out


# --- the bench ------------------------------------------------------------------------------


def reference_for(turns: list[Path], hearing: Hearing, limit: int) -> list[tuple[Path, str]]:
    path = BENCH / "reference.json"
    ref = json.loads(path.read_text("utf-8")) if path.exists() else {}
    picked = []
    for f in turns:
        key = f"{f.parent.name}/{f.name}"
        if key not in ref:
            pcm, _ = read_wav(f)
            text, dropped = hearing.heard(hearing.transcribe(wav_bytes(pcm, 16000)))
            ref[key] = "" if dropped else text
        if ref[key] and len(normalize(ref[key])) >= 4:
            picked.append((f, ref[key]))
        if len(picked) >= limit:
            break
    path.write_text(json.dumps(ref, ensure_ascii=False, indent=1), "utf-8")
    return picked


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=24, help="kiek kliento ėjimų")
    ap.add_argument("--snr", nargs="+", default=["clean", "as_is", "10", "0"])
    ap.add_argument("--variant", nargs="+", default=["none"], choices=sorted(VARIANTS))
    ap.add_argument("--phantoms", type=int, default=20, help="kiek vien fono atkarpų")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--show", type=int, default=0, help="parodyti blogiausius ėjimus")
    ap.add_argument(
        "--bank",
        choices=["room", "all"],
        default="room",
        help="fonas: room — tik tam įrašyti skambučiai (BACKGROUND_ONLY); all — ir tarpai",
    )
    args = ap.parse_args()

    calls = phone_calls()
    bank = background_bank(calls, pure=args.bank == "room")
    if not bank:
        print("nėra telefono režimo įrašų su fonu (PHONE_LINE=on, 8 kHz)")
        return 1
    rng = random.Random(args.seed)
    hearing = Hearing()
    turns = reference_for(clean_turns(args.limit, args.seed), hearing, args.limit)
    bank_s = sum(len(b) for b in bank) / RATE
    print(
        f"ėjimų {len(turns)}, fono {len(bank)} atkarpų / {bank_s:.0f} s iš {len(calls)} skambučių, "
        f"fono lygis {np.median([dbfs(b) for b in bank]):.0f} dBFS"
    )

    # One fixed background per turn, so every variant hears the same room.
    def background(n: int) -> np.ndarray:
        clip = bank[rng.randrange(len(bank))]
        reps = int(np.ceil(n / len(clip)))
        return np.tile(clip, reps)[:n]

    cases = []
    for f, ref in turns:
        pcm16, _ = read_wav(f)
        speech = to_8k(pcm16)
        lead = np.zeros(int(LEAD_S * RATE), np.int16)
        placed = np.concatenate([lead, speech, lead])
        cases.append((f, ref, placed, background(len(placed))))
    # The room alone: a recorded room is heard once, whole; gaps of calls by random 4 s.
    if args.bank == "room":
        phantom_clips = list(bank)
    else:
        phantom_clips = [background(int(4 * RATE)) for _ in range(args.phantoms)]
    speech_db = float(np.median([dbfs(p[p != 0]) for _, _, p, _ in cases]))

    rows, worst, phantom_texts = [], [], []
    for vname in args.variant:
        v = VARIANTS[vname]
        for snr in args.snr:
            cers, lost, extra = [], 0, 0
            for f, ref, placed, bg in cases:
                if snr == "clean":
                    pcm = line(placed)
                else:
                    pcm = line(mix(placed, bg, None if snr == "as_is" else float(snr)))
                heard = hearing.hear(pcm, v)
                kept = [h["text"] for h in heard if not h["dropped"]]
                text = " ".join(kept)
                c = min(cer(ref, text), 1.0)
                cers.append(c)
                lost += not kept
                extra += max(len(kept) - 1, 0)
                worst.append((c, vname, snr, f"{f.parent.name[-4:]}/{f.name}", ref, text))
            phantoms = 0
            if snr != "clean":
                for clip in phantom_clips:
                    # the room as loud as in the mix: a typical turn's level minus the SNR
                    room = clip if snr == "as_is" else scale_to(clip, speech_db - float(snr))
                    for h in hearing.hear(line(room), v):
                        if not h["dropped"]:
                            phantoms += 1
                            phantom_texts.append((vname, snr, h["text"]))
            rows.append(
                (
                    vname,
                    snr,
                    float(np.mean(cers)),
                    float(np.median(cers)),
                    lost,
                    extra,
                    phantoms if snr != "clean" else None,
                )
            )
            print(
                f"  {vname:6} {snr:6} CER {np.mean(cers):5.1%}  prarasta {lost:2}  "
                f"papildomų atkarpų {extra:2}  fantomų {phantoms if snr != 'clean' else '-'}",
                flush=True,
            )
    hearing.save()

    print(
        f"\n{'variantas':9} {'fonas':6} {'CER vid.':>8} {'CER med.':>8} {'prarasta':>8} "
        f"{'papild.':>7} {'fantomai':>8}"
    )
    for vname, snr, mean, med, lost, extra, ph in rows:
        print(
            f"{vname:9} {snr:6} {mean:8.1%} {med:8.1%} {lost:8} {extra:7} "
            f"{'-' if ph is None else ph:>8}"
        )
    print(f"\nASR užklausų (naujų): {hearing.calls}")

    if args.show:
        print("\nBlogiausi:")
        for c, vname, snr, name, ref, text in sorted(worst, reverse=True)[: args.show]:
            print(f"  {c:4.0%} {vname}/{snr} {name}\n       turi: {ref}\n    išgirdo: {text}")

    if args.show and phantom_texts:
        print("\nFantomai (vien fonas → „kliento žodžiai“):")
        for vname, snr, text in phantom_texts[: args.show]:
            print(f"  {vname}/{snr}: {text}")

    out = BENCH / f"noise_bench_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(
        json.dumps({"args": vars(args), "rows": rows}, ensure_ascii=False, indent=1), "utf-8"
    )
    print(f"\n{out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
