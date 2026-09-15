"""The working hypothesis — the telemetry cause the call is testing, the evidence notes
behind it, and how it settles (confirmed / rejected)."""

from __future__ import annotations

from ..contract.locale import phrase_or


def open_hypothesis(state, rt, reason: str | None) -> None:
    """A fresh verdict = a new belief. Seeds it with what the telemetry showed."""
    if not reason:
        return
    h = state.diagnosis.hypothesis
    if h and h.get("cause") == reason and h.get("status") == "testing":
        return  # same belief, still being tested — keep its evidence
    # The ANALYSIS fuses BOTH sides (Step 2): telemetry is the first evidence,
    # the caller's anamnesis (when it broke / after what) the second — so the
    # agent reasons and narrates from the full picture ("telemetrija rodo X, o
    # klientas sako dingo po audros").
    because = [phrase_or(f"verdict.{reason}.gloss", reason)]
    s = state
    if s.intake.anamnesis_when or s.intake.anamnesis_trigger:
        bits = []
        if s.intake.anamnesis_when:
            when = phrase_or(f"anamnesis.when.{s.intake.anamnesis_when}", s.intake.anamnesis_when)
            bits.append(f"dingo {when}")
        if s.intake.anamnesis_trigger:
            trigger = phrase_or(
                f"anamnesis.trigger.{s.intake.anamnesis_trigger}", s.intake.anamnesis_trigger
            )
            bits.append(f"po: {trigger}")
        because.append("klientas sako " + ", ".join(bits))
    state.diagnosis.hypothesis = {
        "cause": reason,
        "because": because,
        "status": "testing",
        "settled_by": None,
    }


def note_evidence(state, rt, text: str) -> None:
    """Add something the ENGINE learned (a telemetry read, a check outcome)."""
    h = state.diagnosis.hypothesis
    if h and text and text not in h["because"]:
        h["because"].append(text)


def settle_hypothesis(state, rt, status: str, settled_by: str) -> None:
    """Close the belief: confirmed (the fix worked / the cause was proven) or
    rejected (it did not hold). Rejected ones are remembered so the engine never
    re-tries them and the agent can say what it already ruled out."""
    h = state.diagnosis.hypothesis
    if not h or h.get("status") != "testing":
        return
    h["status"] = status
    h["settled_by"] = settled_by
    if status == "rejected":
        state.diagnosis.rejected_hypotheses.append({"cause": h["cause"], "settled_by": settled_by})
