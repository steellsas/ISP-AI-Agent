"""What the call's PROBLEM is — the policy over this turn's problem reading (wave 1c).

perceive hears a label ("this sounded like internet_down"); what the call is ABOUT is a
decision:

- the PRIMARY problem is the caller's stated call reason and never flips mid-call (an STT
  garble once switched it to billing live);
- a later mention of ANOTHER fault becomes a SECONDARY problem — noted, asked about at the
  end, listed on the ticket;
- a label outside the agent's competence (not_ours / chat) never becomes the problem: the
  boundary reply answers it instead (2026-09-02);
- before identification a clearer self-correction may still replace the primary.

It writes no plan: it is the bookkeeping the rules below it read. Before wave 1c this
lived in perceive, which therefore decided as well as read.
"""

from __future__ import annotations

from typing import Any


def apply_readings(state: Any, rt: Any) -> None:
    """Commit what this turn's readings mean for the call."""
    _apply_caller_relation(state, rt)
    _apply_problem(state, rt)


def _apply_caller_relation(state: Any, rt: Any) -> None:
    """The answer to the holder clarification: it records WHO is calling (never a gate,
    D-09) and closes the clarification."""
    relation = state.turn.caller_relation_reading
    if not relation:
        return
    s = state
    s.identity.holder_clarify_open = False
    s.identity.holder_clarify_asked = False
    # The same answer often CORRECTS the name: live 2026-09-30 the caller said „Ne, mano vardu
    # Giedrius" and heard „Gedriau" for the rest of the call — the name question was already
    # closed, so nothing was listening. A name given here wins over what was misheard.
    from ...perceive.caller import extract_caller_name

    heard = state.dialog.last_heard or ""
    corrected = extract_caller_name(heard)
    # Only a name the caller gives as THEIR OWN corrects the record. Live 2026-10-07:
    # „Taip, mano tėtis Gedrius yra vardu" renamed the caller Andrius to the HOLDER Gedrius,
    # and „Aršku ačių lauksu" renamed Rasa to „Aršku" (wave 10, V5).
    from ...contract.locale import vocab

    own = any(m in heard.lower() for m in vocab("caller_own_name_markers"))
    if corrected and own and corrected != s.identity.caller_name:
        rt.tracer.emit("caller_intro", name=corrected, was=s.identity.caller_name, corrected=True)
        s.identity.caller_name = corrected
    if relation != "unknown":
        s.identity.caller_relation = relation
        rt.tracer.emit(
            "caller_intro", name=s.identity.caller_name, relation=relation, clarified=True
        )


def _apply_problem(state: Any, rt: Any) -> None:
    """Commit / file this turn's problem reading (no-op without one)."""
    problem = state.turn.problem_reading
    if not problem:
        return
    from ...intents import BOUNDARY_POLICIES, problem_policy

    s = state
    policy = problem_policy(problem)
    if policy in BOUNDARY_POLICIES:
        if s.intake.problem_type is None:
            s.intake.boundary_problem = problem  # one-shot for the boundary reply
        return
    if s.intake.problem_type is None:
        s.intake.problem_type = problem
        rt.tracer.emit("decision", intent="problem", action="primary", value=problem)
        return
    if problem == s.intake.problem_type:
        return
    if _is_secondary(state, problem, policy):
        s.intake.secondary_problems.append(
            {
                "type": problem,
                "text": (s.dialog.last_heard or "").strip()[:120],
                "turn": s.dialog.turn_count,
            }
        )
        rt.tracer.emit("decision", intent="problem", action="secondary", value=problem)
        return
    if not s.identity.customer_id and s.resolution.procedure is None:
        # Early self-correction, before anything was checked, is fine.
        s.intake.problem_type = problem
        rt.tracer.emit("decision", intent="problem", action="corrected", value=problem)


def _is_secondary(state: Any, problem: str, policy: str | None) -> bool:
    """Another FAULT mentioned while one is being solved. A request (billing…) is not a
    secondary tech problem — it gets its own ticket later (F-28); a garble
    ("Žemės gatvės") is not a complaint."""
    s = state
    return (
        policy == "solve"
        # Being solved = identified and worked on. v1 marked it with `resolution.procedure`,
        # which a v2 Case call never fills, so a TV problem mentioned mid-fix was dropped
        # and never reached the ticket (wave 10, S6).
        and (s.resolution.procedure is not None or bool(s.identity.customer_id))
        and not s.closing.case_closed
        and not s.ticket.stage
        and len((s.dialog.last_heard or "").split()) >= 3
        and not any(x.get("type") == problem for x in s.intake.secondary_problems)
    )
