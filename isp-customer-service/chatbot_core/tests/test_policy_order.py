"""The policy chain keeps today's precedence (docs/refactoring/M4_decide.md §5): the
families are ported top-down, so the chain is always a prefix of the §5 order."""

from agent.decide.policy import RULES

# §5 rows, highest precedence first.
SECTION_5 = [
    (1, "dialog.greeting"),
    (2, "closing"),
    (3, "ticket"),
    (4, "dialog.end_confirm_answer"),
    (5, "identification.reopen_confirm_answer"),
    (6, "dialog.cannot_now"),
    (7, "dialog.farewell_mid_process"),
    (8, "identification.caller_intro"),
    (9, "identification"),
    (10, "identification.address_correction"),
    (11, "dialog.callback_goodbye_due"),
    (12, "side_topic"),
    (13, "diagnosis.hypothesis_confirm"),
    (14, "dialog.confirm_end"),
    (15, "inform"),
    (16, "procedure"),
    (17, "diagnosis"),
    (18, "dialog.stuck_backstop"),
    (19, "dialog.wait_ack"),
    (20, "dialog.free_reply"),
]


def test_rules_follow_section_5_order():
    ported = [(row, family) for row, family, _rule in RULES]
    assert ported == SECTION_5[: len(ported)]
