"""Test helper: turn a SimpleNamespace fake engine into a call the flows accept."""

from types import SimpleNamespace

# The flow function behind each former ReactAgent delegate name a fake may carry.
_FLOW_OF = {
    "_abort_ticket_to_solving": "agent.ticket_flow.abort_ticket_to_solving",
    "_advance_escalate": "agent.walker_flow.advance_escalate",
    "_advance_instruct": "agent.walker_flow.advance_instruct",
    "_advance_line_check": "agent.walker_flow.advance_line_check",
    "_advance_reboot_check": "agent.walker_flow.advance_reboot_check",
    "_advance_resolution": "agent.walker_flow.advance_resolution",
    "_advance_restored": "agent.walker_flow.advance_restored",
    "_advance_see_device": "agent.walker_flow.advance_see_device",
    "_augment_resolve_result": "agent.narrator_flow.augment_resolve_result",
    "_augment_tool_result": "agent.narrator_flow.augment_tool_result",
    "_begin_ticket_dialogue": "agent.ticket_flow.begin_ticket_dialogue",
    "_block_uncorroborated_escalate": "agent.walker_flow.block_uncorroborated_escalate",
    "_bridge_fail_step": "agent.solver_flow.bridge_fail_step",
    "_build_messages": "agent.narrator_flow.build_messages",
    "_build_solver_context": "agent.solver_flow.build_solver_context",
    "_classify_confirm_and_route": "agent.walker_flow.classify_confirm_and_route",
    "_classify_instruct_and_advance": "agent.walker_flow.classify_instruct_and_advance",
    "_detect_confirm": "agent.walker_flow.detect_confirm",
    "_drive": "agent.solver_flow.drive",
    "_drive_escalate": "agent.solver_flow.drive_escalate",
    "_drive_propose_fix": "agent.solver_flow.drive_propose_fix",
    "_emit_rag_injection": "agent.narrator_flow.emit_rag_injection",
    "_engine_resolve_from_slots": "agent.perception_flow.engine_resolve_from_slots",
    "_evidence_drive": "agent.evidence_drive.evidence_drive",
    "_evidence_question_open": "agent.evidence_drive.evidence_question_open",
    "_execute_tool_calls": "agent.executor_flow.execute_tool_calls",
    "_finish_ticket_dialogue": "agent.ticket_flow.finish_ticket_dialogue",
    "_fresh_diagnose_reason": "agent.walker_flow.fresh_diagnose_reason",
    "_goto_step": "agent.walker_flow.goto_step",
    "_identification_scripted_reply": "agent.identification_flow.identification_scripted_reply",
    "_ingest_client_evidence": "agent.perceive.evidence.ingest_client_evidence",
    "_mark_step_presented": "agent.narrator_flow.mark_step_presented",
    "_maybe_close_inform": "agent.closing_flow.maybe_close_inform",
    "_maybe_end_on_goodbye": "agent.closing_flow.maybe_end_on_goodbye",
    "_maybe_finish": "agent.closing_flow.maybe_finish",
    "_negation_clarify_reply": "agent.evidence_drive.negation_clarify_reply",
    "_note_evidence": "agent.walker_flow.note_evidence",
    "_on_task_question": "agent.perceive.side_topic.on_task_question",
    "_open_hypothesis": "agent.walker_flow.open_hypothesis",
    "_plug_report": "agent.solver_flow.plug_report",
    "_pre_turn_guards": "agent.perception_flow.pre_turn_guards",
    "_prefill_slots_from_text": "agent.perceive.slots.prefill_slots_from_text",
    "_preflight_phone": "agent.identification_flow.preflight_phone",
    "_prune_history": "agent.narrator_flow.prune_history",
    "_refresh_diagnosis": "agent.solver_flow.refresh_diagnosis",
    "_register_ticket_from_state": "agent.executor_flow.register_ticket_from_state",
    "_registration_claim_guard": "agent.ticket_flow.registration_claim_guard",
    "_reject_and_rediagnose": "agent.walker_flow.reject_and_rediagnose",
    "_reopen_identification": "agent.identification_flow.reopen_identification",
    "_result_narration_tail": "agent.narrator_flow.result_narration_tail",
    "_route_to": "agent.walker_flow.route_to",
    "_scoped_tools_schema": "agent.narrator_flow.scoped_tools_schema",
    "_scripted_wait_ack": "agent.walker_flow.scripted_wait_ack",
    "_settle_hypothesis": "agent.walker_flow.settle_hypothesis",
    "_shadow_solve": "agent.solver_flow.shadow_solve",
    "_simulate_bridge_connection": "agent.executor_flow.simulate_bridge_connection",
    "_simulate_router_reboot": "agent.executor_flow.simulate_router_reboot_action",
    "_state_facts_block": "agent.narrator_flow.state_facts_block",
    "_ticket_need": "agent.ticket_flow.ticket_need",
    "_ticket_stage_reply": "agent.ticket_flow.ticket_stage_reply",
    "_turn_may_advance": "agent.walker_flow.turn_may_advance",
    "_update_state_from_observation": "agent.narrator_flow.update_state_from_observation",
    "_walk_resolution": "agent.walker_flow.walk_resolution",
    "_wants_to_keep_solving": "agent.ticket_flow.wants_to_keep_solving",
    "anchor_text": "agent.dialog_utils.anchor_text",
    "classify_side_topic": "agent.perceive.side_topic.classify_side_topic",
    "ensure_action_done": "agent.walker_flow.ensure_action_done",
    "ensure_diagnosed": "agent.walker_flow.ensure_diagnosed",
    "solver_drive_turn": "agent.solver_flow.solver_drive_turn",
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
