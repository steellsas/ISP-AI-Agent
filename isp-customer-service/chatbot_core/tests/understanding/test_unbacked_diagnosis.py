"""LLM diagnozė be variklio (live 2026-11-23, call 9): mid-address the model said „Panašu, kad
mūsų linija yra gerai, tad problema gali būti jūsų namuose". No line was read — not spoken."""

FUNCTION = "Diagnozė be patikros"


def test_a_finding_before_the_line_is_read_is_not_spoken(make_state):
    from agent.speak.node import unbacked_diagnosis

    state = make_state("+37060020105")
    said = "Panašu, kad mūsų linija yra gerai, tad problema gali būti jūsų namuose."
    assert unbacked_diagnosis(state, said)
    assert not unbacked_diagnosis(state, "Ar galėtumėte pasakyti tikslų namo numerį?")
    assert not unbacked_diagnosis(state, "Suprantu — dingo internetas. Patikrinsiu liniją.")


def test_after_the_line_is_read_it_is(make_state):
    from agent.speak.node import unbacked_diagnosis

    state = make_state("+37060020105")
    state.identity.customer_id = "CUST105"
    state.diagnosis.verdicts = {"network": {"cause": "healthy_to_router"}}
    assert not unbacked_diagnosis(state, "Linija iki jūsų veikia, problema gali būti įrenginyje.")
