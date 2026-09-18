"""Test helper: turn a SimpleNamespace fake engine into a call the flows accept."""

from types import SimpleNamespace

# The engine function behind each legacy delegate name a fake may carry.
_FLOW_OF = {
    "_abort_ticket_to_solving": "agent.decide.rules.ticket.abort_ticket_to_solving",
    "_advance_escalate": "agent.decide.procedure.advance_escalate",
    "_advance_instruct": "agent.decide.procedure.advance_instruct",
    "_advance_line_check": "agent.decide.procedure.advance_line_check",
    "_advance_reboot_check": "agent.decide.procedure.advance_reboot_check",
    "_advance_resolution": "agent.decide.procedure.advance",
    "_advance_restored": "agent.decide.procedure.advance_restored",
    "_advance_see_device": "agent.decide.procedure.advance_see_device",
    "_augment_resolve_result": "agent.execute.observe.augment_resolve_result",
    "_augment_tool_result": "agent.execute.observe.augment_tool_result",
    "_begin_ticket_dialogue": "agent.execute.ticket.begin_ticket_dialogue",
    "_block_uncorroborated_escalate": "agent.decide.procedure.block_uncorroborated_escalate",
    "_bridge_fail_step": "agent.decide.rules.diagnosis.bridge_fail_step",
    "_build_solver_context": "agent.decide.rules.diagnosis.build_solver_context",
    "_classify_confirm_and_route": "agent.decide.procedure.classify_confirm_and_route",
    "_classify_instruct_and_advance": "agent.decide.procedure.classify_instruct_and_advance",
    "_detect_confirm": "agent.decide.procedure.detect_confirm",
    "_drive": "agent.decide.rules.diagnosis.drive",
    "_drive_escalate": "agent.decide.rules.diagnosis.drive_escalate",
    "_drive_propose_fix": "agent.decide.rules.diagnosis.drive_propose_fix",
    "_emit_rag_injection": "agent.execute.step.emit_rag_injection",
    "_engine_resolve_from_slots": "agent.decide.rules.identification.engine_resolve_from_slots",
    "_evidence_drive": "agent.decide.rules.evidence.evidence_drive",
    "_evidence_question_open": "agent.decide.rules.evidence.evidence_question_open",
    "_finish_ticket_dialogue": "agent.execute.ticket.finish_ticket_dialogue",
    "_fresh_diagnose_reason": "agent.execute.diagnosis.fresh_diagnose_reason",
    "_goto_step": "agent.decide.procedure.goto_step",
    "_identification_scripted_reply": "agent.decide.rules.reply.scripted_words",
    "_ingest_client_evidence": "agent.perceive.evidence.ingest_client_evidence",
    "_mark_step_presented": "agent.execute.step.mark_step_presented",
    "_maybe_close_inform": "agent.decide.rules.closing.maybe_close_inform",
    "_maybe_end_on_goodbye": "agent.execute.say.maybe_end_on_goodbye",
    "_maybe_finish": "agent.decide.rules.closing.maybe_finish",
    "_negation_clarify_reply": "agent.decide.rules.evidence.negation_clarify_reply",
    "_note_evidence": "agent.decide.hypothesis.note_evidence",
    "_on_task_question": "agent.perceive.side_topic.on_task_question",
    "_activate_hypothesis": "agent.decide.hypothesis.activate_hypothesis",
    "_plug_report": "agent.decide.rules.diagnosis.plug_report",
    "_pre_turn_guards": "agent.decide.rules.head.turn_head",
    "_prefill_slots_from_text": "agent.perceive.slots.prefill_slots_from_text",
    "_preflight_phone": "agent.execute.identification.preflight_phone",
    "_prune_history": "agent.speak.history.prune_history",
    "_refresh_diagnosis": "agent.decide.rules.diagnosis.refresh_diagnosis",
    "_register_ticket_from_state": "agent.executor_flow.register_ticket_from_state",
    "_registration_claim_guard": "agent.execute.ticket.registration_claim_guard",
    "_reject_and_rediagnose": "agent.decide.procedure.reject_and_rediagnose",
    "_reopen_identification": "agent.decide.rules.identification.reopen_identification",
    "_result_narration_tail": "agent.speak.context_card.result_narration_tail",
    "_route_to": "agent.decide.procedure.route_to",
    "_scripted_wait_ack": "agent.decide.rules.dialog.scripted_wait_ack",
    "_settle_hypothesis": "agent.decide.hypothesis.settle_hypothesis",
    "_simulate_bridge_connection": "agent.executor_flow.simulate_bridge_connection",
    "_simulate_router_reboot": "agent.executor_flow.simulate_router_reboot_action",
    "_context_card": "agent.speak.context_card.context_card",
    "_ticket_need": "agent.decide.rules.ticket.ticket_need",
    "_ticket_stage_reply": "agent.decide.rules.ticket.ticket_stage_reply",
    "_turn_may_advance": "agent.decide.procedure.turn_may_advance",
    "_update_state_from_observation": "agent.execute.observe.update_state_from_observation",
    "_walk_resolution": "agent.decide.procedure.walk_resolution",
    "_wants_to_keep_solving": "agent.decide.rules.ticket.wants_to_keep_solving",
    "anchor_text": "agent.dialog_utils.anchor_text",
    "classify_side_topic": "agent.perceive.side_topic.classify_side_topic",
    "ensure_action_done": "agent.execute.diagnosis.ensure_action_done",
    "ensure_diagnosed": "agent.execute.diagnosis.ensure_diagnosed",
    "solver_drive_turn": "agent.decide.rules.diagnosis.solver_drive_turn",
}


def as_call(monkeypatch, fake):
    """Give `fake` a runtime and route its delegate lambdas (e.g. `_goto_step`)
    through the flow functions they replace."""
    fake.runtime = SimpleNamespace(
        tracer=getattr(fake, "tracer", None),
        tools=getattr(fake, "tools", None),
        config=getattr(fake, "config", None),
        engine=fake,
    )
    for attr, target in _FLOW_OF.items():
        fn = getattr(fake, attr, None)
        if fn is not None:
            assert monkeypatch is not None, f"{attr} on a fake needs monkeypatch"
            monkeypatch.setattr(target, lambda state, rt, *a, _fn=fn, **k: _fn(*a, **k))
    return fake
