"""The context card — the engine's current truth for the speaking LLM (D-02).

Every line comes from typed state or the turn's plan: what is known, what is being
tested, what the caller just said, and the ONE goal this reply must reach. No line may
change WHAT happens — the rules in `decide` chose that; the card only says what the
speaker may say and must not say.

Sections, in the order they carry weight on a phone call:
  SIDE TOPIC / TICKET DIALOGUE  the turn is off the fault path — they lead
  DELIVERY                      what the caller did or did not hear (voice)
  JUST HEARD                    this turn's understanding pass
  CALLER / PROBLEM / TICKET     durable identity and case facts
  CASE                          closed, registered, resolved states
  DIALOGUE                      stuck, silence, waiting, plain-words requests
  HYPOTHESIS / EVIDENCE         what we believe, why, what is settled and open
  STEP                          the procedure step's goal, hint and playbook
  PLAN GOAL                     the one instruction for this reply
"""

from __future__ import annotations

import json  # noqa: F401  (used by moved bodies)
import os  # noqa: F401
import re  # noqa: F401
from typing import Any  # noqa: F401

from ..contract.locale import phrase, phrase_or

HEADER = "CONTEXT CARD (the engine's truth for this reply — never re-ask what it holds):"


def context_card(state, rt) -> str | None:
    """The card for this turn, or None when nothing is known yet."""
    lines: list[str] = []
    for section in (
        _side_topic,
        _ticket_dialogue,
        _delivery,
        _just_heard,
        _identification_notes,
        _case_facts,
        _tool_trouble,
        _case_step,
        _dialogue_state,
        _plan_goal,
        _recall_and_notes,
    ):
        lines += section(state, rt) or []
    if not lines:
        return None
    return HEADER + "\n" + "\n".join(f"- {line}" for line in lines)


# --- the turn is off the fault path ------------------------------------------------------


def _faq_answer(state, rt, entry: dict) -> str:
    """The answer to a side question — from the NEWS's own facts when that news has been
    delivered in this call (live 2026-09-23: the agent read out a debt of 49,98 € and then
    answered "tikslios sumos aš nematau")."""
    news = entry.get("answer_from_news")
    if news:
        from ..inform import inform_text

        reason = (state.diagnosis.verdicts.get("network") or {}).get("reason")
        if reason == news:
            said = inform_text(state, rt, reason, key="asked_again_key")
            if said:
                return said
    return phrase(entry["answer_key"])


def _kb_answer(state, rt) -> str:
    """Žinių bazės atsakymas atviram klausimui — kai FAQ jo neturi (radinys AK, 4b banga).

    Nuo E3b ieškoma ne viso kliento sakinio, o POREIKIO (`knowledge_need`). Du dalykai iš to:

      * paieška gauna MŪSŲ žodžius, o ne visą frazę. Išmatuota, kad tai svarbiausia: kliento sakiniu
        hit@1 54 % / hit@2 57 %, o agento poreikiu (kai jį formuluoja kortelė) 90 % / 95 %;
      * jei apie tai ieškoti neleidžiama — NEIEŠKOM. Ne mūsų sritis („koks oras", „autoremontas"),
        ne mūsų paskirtis („kurį routerį pirkti") ir paties prietaiso bėdos („Windows nepasileidžia")
        žinių bazės net nepasiekia. Atsisakymas įrašomas į žurnalą, kad ribą vėliau būtų galima
        peržiūrėti faktais, o ne nuomone.
    """
    from ..knowledge_base import find
    from ..knowledge_need import Refusal, device_markers, from_caller

    # Which family of device this caller actually has: the catalogue already answers that
    # from the line's own reading ("TP-Link Archer C80" -> tplink), and `level` names the file
    # that won — exactly the tag the documents carry.
    signals = (state.diagnosis.verdicts.get("network") or {}).get("signals") or {}
    equipment = None
    if signals.get("device_model") or signals.get("device_type"):
        from ..equipment import for_signals

        device = for_signals(signals)
        equipment = device.level if device else None

    need = from_caller(
        state.dialog.last_heard or "",
        equipment=equipment,
        # ŠIO skambučio paslauga: TV dokumentas neturi būti kandidatas interneto gedime, o neutralios
        # žinios (įrangos instrukcija, procedūra, FAQ) praleidžiamos per bet kurį gedimą.
        problem=_service_of(state),
    )
    # AGENTO sprendimas, ko jam reikia: dokumentą jis pasirinko iš savo žinių žemėlapio dar
    # suprasdamas ėjimą (`understand`). Kliento žodžiai toliau reikalingi, bet tik SKYRIUI tame
    # dokumente ir patikimumui. Išmatuota: taip randama 66 %, ieškant vien kliento sakiniu — 57 %.
    routed = str((getattr(state.turn, "understanding", None) or {}).get("knowledge") or "") or None
    if isinstance(need, Refusal):
        if rt is not None and getattr(rt, "tracer", None) is not None:
            rt.tracer.emit("knowledge", refused=need.why, said=need.said[:60])
        return ""
    found = _in_routed_document(need, routed) or find(
        need.words,
        equipment=need.equipment,
        problem=need.problem,
        # Klientas įvardino telefoną ar kompiuterį: pirmumas TO įrenginio instrukcijai.
        prefer=device_markers(need.device),
        limit=2,
    )
    if rt is not None and getattr(rt, "tracer", None) is not None:
        rt.tracer.emit(
            "knowledge",
            asked_by=need.asked_by,
            words=need.words[:60],
            found=",".join(p.source for p in found)[:80] or "-",
            sure=any(p.sure for p in found),
        )
    if not found:
        return ""
    said = " ".join(f"[{p.kind}: {p.title}] {p.text}" for p in found)
    if need.device and all(p.specific is False for p in found):
        # Turim bendrą tvarką, bet ne to įrenginio. Andrius (2026-09-24): „jei to nėra, sako —
        # neturiu informacijos, kaip toks įrenginys nustatomas, bet galiu bendra tvarka pasakyti."
        said = (
            f"(NO instructions for THIS device — say first that you do not have the exact steps "
            f"for their {need.device}, then give this GENERAL procedure) {said}"
        )
    if all(not p.sure for p in found):
        # Spėjimas, ne atsakymas: agentas privalo pasakyti, kad nėra tikras, ir patikslinti.
        # Iki E1 tokiu atveju būdavo grąžinama NIEKO, o modelis improvizuodavo.
        return f"(NOT SURE this answers the question, say so and ask to rephrase) {said}"
    return said


def _in_routed_document(need, routed: str | None):
    """Skyrius TAME dokumente, kurį agentas pasirinko — arba nieko, ir tada ieškom įprastai.

    Kodėl dokumentas iš agento, o skyrius iš kliento žodžių: ieškant vien poreikiu balas normuojamas
    pagal poreikį ir tampa 1,000 — viskas atrodytų „tvirta". Kliento žodžiai išlaiko patikimumą
    sąžiningą, o agento pasirinkimas pataiso vietą. Jei jo dokumente nieko nėra, GELBSTI įprasta
    paieška: be to septyni klausimai iš 68 būtų likę be atsakymo (išmatuota).
    """
    if not routed:
        return []
    from ..knowledge_base import find
    from ..knowledge_need import device_markers

    return find(
        need.words,
        source=routed,
        prefer=device_markers(need.device),
        limit=2,
    )


def _service_of(state) -> str | None:
    """Kurios paslaugos gedimą sprendžia šio skambučio kortelė (`internet`), arba None.

    `case.fault` yra KORTELĖS vardas (`dhcp_silent`), ne problemos šeima — paduoti jį filtrui
    reikštų išmesti visus gedimų dokumentus. Šeimą pasako kortelės `service`, o `any` reiškia
    „netaikoma": tiketo būsena ar skolos žinia neturi savo problemų šeimos.
    """
    if not state.case.fault:
        return None
    from ..contract import cards as catalog

    card = catalog.cards().get(state.case.fault)
    service = getattr(card, "service", None)
    return service if service and service != "any" else None


def _mark_written_step_said(state) -> None:
    """A written step counts as SAID when a reply is actually being built for it.

    Marking it when the plan was built was wrong: on a turn the identification rule owned, the
    guide plan existed, was never spoken, and the caller's next words finished a step they had
    never heard (2026-09-23).
    """
    if str((state.turn.plan or {}).get("rule") or "") != "case.guide":
        return
    state.case.guide_said = state.case.guide_step


def _asked_how(state, rt) -> list[str]:
    """Klientas paklausė „kaip…", o ėjimas paleistas per narratorių (`question_passthrough`).

    Iki 4b bangos šiam ėjimui kortelė nesakė NIEKO — ir modelis improvizavo: į „kaip pakeisti
    wifi slaptažodį" atsakė „užregistruosiu jūsų klausimą" (gyvai 2026-09-23). Dabar atsakymas
    turi šaltinį: pažymėta žinių bazė (įrangos instrukcija, konfigūravimo algoritmas, patarimas),
    atfiltruota pagal ŠIO kliento įrangą. Nieko neradus — sąžiningai pasakoma, kad nežino.
    """
    plan = state.turn.plan or {}
    if str(plan.get("rule") or "") != "dialog.question_passthrough":
        return []
    if state.turn.side_topic_active:
        return []  # the side-topic section owns that turn, with its own FAQ/news answer
    said = _kb_answer(state, rt)
    if not said:
        return [
            "THE CALLER ASKED HOW: we have no written answer for it. Say honestly that you "
            "cannot advise on that, promise nothing, invent nothing (no registration, no "
            "prices, no deadlines), and return to what the engine is waiting for."
        ]
    if said.startswith("(NOT SURE"):
        # Spėjimas nėra atsakymas į „kaip…": žingsnių sakyti negalima, nes gali būti ne tos
        # įrangos ar ne to dalyko. Todėl patikslinam, o ne skaitom (E1, trys lygiai).
        return [
            "THE CALLER ASKED HOW: the written knowledge we found may not be about their "
            "question, so do NOT read steps from it. Say in one sentence that you are not sure "
            f"you understood, ask them to say it in other words, and invent nothing. {said}"
        ]
    return [
        "THE CALLER ASKED HOW: answer in ONE or TWO sentences using ONLY this written "
        f"knowledge — {said} Invent nothing beyond it (no prices, deadlines, promises, no "
        # Paskutinė sąžiningumo linija. Balas negali atskirti „apie tą temą" nuo „atsako į tą
        # klausimą": „ar wifi kenkia sveikatai" gauna 0,26 ir laikomas tvirtu, nes WiFi tikrai mūsų
        # tema. Ar tekstas ATSAKO į klausimą, sprendžia modelis — tai kaip tik tas darbas, kurį jis
        # moka, o rikiuotojas ne.
        "registration). KEEP the concrete detail the knowledge names — an address like 192.168.0.1, "
        "a setting's name, where to look — because that is what the caller acts on; a summary "
        "without it is not an answer. If this knowledge does not actually answer what they asked, "
        "say honestly that you cannot advise on that instead of stretching it. Then return to what "
        "the engine is waiting for."
    ]


def _side_topic(state, rt) -> list[str]:
    """A deviation: the ONLY permitted content is the FAQ hit (or an honest "not my
    area"), then the return anchor — the engine's exact pending question."""
    if not state.turn.side_topic_active:
        return []
    from ..dialog_utils import anchor_text
    from ..faq import match as faq_match

    hits = faq_match(state.dialog.last_heard)
    known = " ".join(f"[{e.get('topic')}] {_faq_answer(state, rt, e)}" for e in hits) or (
        # Beyond the five FAQ topics there is a tagged knowledge base — equipment
        # instructions, configuration algorithms, tips (wave 4b, finding AK). It answers, or
        # the agent says honestly that it is not its area.
        _kb_answer(state, rt)
        or "(NO KNOWN ANSWER for this topic - say politely that it is not your area)"
    )
    # The topic is DETERMINISTIC when the FAQ matched — the model once copied a prompt
    # example ("Klausiate apie kainą") for a topic the caller never raised.
    topic = phrase(f"faq_topic.{hits[0]['topic']}") if hits else ""
    naming = (
        f"The caller's topic: {topic}. "
        if topic
        else "Name the topic from the caller's LAST phrase - no other topic. "
    )
    return [
        "SIDE TOPIC: the caller asked about something other than the fault. "
        f"{naming}Answer in ONE or TWO sentences using ONLY these known answers: "
        f"{known} Invent NOTHING (no sums, deadlines, promises). Then ALWAYS return to the "
        f"fault by repeating: „{anchor_text(state, rt)}“"
    ]


def _ticket_dialogue(state, rt) -> list[str]:
    """The caller asked something instead of answering the contact question."""
    from ..execute.ticket import fmt_phone

    out: list[str] = []
    if state.ticket.stage in ("phone", "hours"):
        from ..decide.rules.ticket import ticket_need

        pending = phrase(
            "identification.ticket_phone"
            if state.ticket.stage == "phone"
            else "identification.ticket_hours"
        )
        out.append(
            "TICKET DIALOGUE: we are registering the fault (reason: "
            f"{ticket_need(state, rt)}). The caller's number: "
            f"{fmt_phone(state.identity.caller_phone) or 'unknown'}. The ticket is NOT "
            "registered yet — never say „užregistravau“. Answer the caller's question in "
            f"ONE sentence and then repeat the question: „{pending}“"
        )
    # A refusal WITH solving content: the dialogue was dropped, the call stays open.
    if state.ticket.resume_fix_note:
        state.ticket.resume_fix_note = False
        out.append(
            "REGISTRATION DECLINED, THE CALLER WANTS TO KEEP SOLVING: say in one sentence "
            "that you are not registering a technician, and GO BACK to the last solving "
            "instruction — repeat it or answer their question about it. Do NOT end the call."
        )
    return out


def _case_step(state, rt) -> list[str]:
    """What the CASE decided this turn (wave 3): the one thing to achieve, and the words the
    equipment catalogue guarantees for this caller's device.

    The v1 packs reached the narrator through the pack's step hint; a v2 module reaches it
    here, which is why this section exists at all — without it the engine decided to
    instruct a reboot and the reply never said so (live probe, S6).
    """
    plan = state.turn.plan or {}
    rule = str(plan.get("rule") or "")
    if not rule.startswith("case."):
        return []
    say = plan.get("say") or {}
    goal, words = say.get("goal"), say.get("text")
    out: list[str] = []
    if goal:
        out.append(f"PLAN GOAL — {goal}. Nothing else in this reply.")
    if words:
        # Precision beats style here: these words come from the equipment catalogue, so the
        # concrete action and the device must survive the paraphrase (full eval: the reboot
        # instruction lost the words "maitinimo laidą" when the model reworded it freely).
        out.append(
            f"SAY THIS STEP: „{words}“ — you may shorten it or lead with a short reaction, "
            "but KEEP the concrete action and the part of the device it names. Do not add "
            "steps of your own and do not replace it with a question."
        )
    out += _step_knowledge(state, rt)
    return out


def _step_knowledge(state, rt) -> list[str]:
    """Gilesnės žinios ŠIAM žingsniui, jei kortelė jų paprašė (`knowledge_need`, E3b).

    Kortelė sprendžia gedimą; žinių bazė ją papildo. Agentas klausia „kokios spalvos lemputė", ir
    jei klientas paklaus „kuri iš jų", atsakymas turi būti po ranka — ne improvizuotas.

    Paieška čia vyksta AGENTO poreikiu, ne kliento sakiniu, ir būtent todėl ji tiksli: išmatuota
    hit@1 90 % prieš 54 %. Žinia paduodama kaip ATSARGA, o ne kaip tai, ką reikia pasakyti — kitaip
    agentas skaitytų instrukciją tada, kai jos niekas neprašė.
    """
    need_text = _current_need(state)
    if not need_text:
        return []
    from ..knowledge_base import find
    from ..knowledge_need import from_card

    need = from_card(need_text, equipment=_equipment_of(state), problem=_service_of(state))
    found = find(need.words, equipment=need.equipment, problem=need.problem, limit=1)
    if rt is not None and getattr(rt, "tracer", None) is not None:
        rt.tracer.emit(
            "knowledge",
            asked_by="card",
            words=need.words[:60],
            found=found[0].source if found else "-",
        )
    if not found:
        return []
    # Atsargai pakanka kelių sakinių. Visa dalis (iki 700 simbolių) kiekviename tų žingsnių ėjime
    # tik ilgina kortelę ir atsakymą, o balse ilgesnis atsakymas kainuoja laiko: D5 pilname balso
    # rinkime dėl to prarado ėjimą ir tiketas nebeįvyko (2026-09-25).
    return [
        "DEEPER KNOWLEDGE for this step (use ONLY if the caller asks about it; do not read it "
        f"out on your own): [{found[0].title}] {found[0].text[:240]}"
    ]


def _current_need(state) -> str | None:
    """Ką šio ėjimo žingsnis deklaravo kaip savo žinių poreikį."""
    plan = state.turn.plan or {}
    need = (plan.get("action") or {}).get("knowledge_need") or (plan.get("say") or {}).get(
        "knowledge_need"
    )
    return str(need) if need else None


def _equipment_of(state) -> str | None:
    """Kliento įrangos lygis iš linijos rodmenų — tas pats tagas, kurį nešasi dokumentai."""
    signals = (state.diagnosis.verdicts.get("network") or {}).get("signals") or {}
    if not (signals.get("device_model") or signals.get("device_type")):
        return None
    from ..equipment import for_signals

    device = for_signals(signals)
    return device.level if device else None


def _tool_trouble(state, rt) -> list[str]:
    """A system we depend on did not answer this turn (wave 2c-4). The narrator must not
    report a check that never ran — it says what is unavailable, in its own words, and the
    plan's goal says what happens instead."""
    trouble = state.turn.tool_trouble
    if not trouble:
        return []
    line = phrase_or(trouble.get("say_key") or "", "")
    if not line:
        return []
    return [
        "A SYSTEM DID NOT ANSWER (do NOT say you checked anything, do not name the system "
        f"or the error): say this in your own words — „{line}“"
    ]


# --- what reached the caller's ear -------------------------------------------------------


def _delivery(state, rt) -> list[str]:
    """Voice delivery notes: a barge-in cut the reply, the caller spoke over it, or the
    question never went out. One-shot — each is consumed as it is rendered."""
    out: list[str] = []
    tail = state.voice.undelivered_tail
    if tail:
        state.voice.undelivered_tail = None
        out.append(
            f"NOT HEARD (the caller cut in): „{tail[:160]}“ — if it matters, say it again "
            "briefly in your own words."
        )
    overlay = state.voice.overlay_heard
    if overlay:
        state.voice.overlay_heard = None
        quoted = " / ".join(f"„{t[:120]}“" for t in overlay)
        out.append(
            f"SPOKEN OVER YOU: {quoted} — take it into account; if it answers your "
            "question, do not ask it again."
        )
    unheard = state.voice.unheard_question
    if unheard:
        state.voice.unheard_question = None
        out.append(
            "YOUR QUESTION NEVER WENT OUT: the caller did not hear it (they cut in "
            "earlier), so their words are NOT an answer to it. React to what they said "
            f"first, then ask it anew in your own words (one „?“): „{unheard[:160]}“"
        )
    return out


def _just_heard(state, rt) -> list[str]:
    """The understanding pass: the acknowledgement that makes the caller feel heard, and
    what they did not understand."""
    u = state.turn.understanding
    if u is None or state.turn.side_topic_active or state.closing.case_closed:
        return []
    out: list[str] = []
    understood = (u.get("understood") or "").strip()
    # The pass's summary is INTERNAL wording, often third-person about the caller; quoted
    # verbatim it became the agent's broadcast thought („Supratau — Paulius atliko veiksmą“
    # spoken TO Paulius). Then the instruction goes out without the quote.
    name = (state.identity.caller_name or "").strip()
    third_person = (bool(name) and name.lower() in understood.lower()) or any(
        m in understood.lower()
        for m in ("klientas", "klientė", "kliente", "naudotojas", "vartotojas")
    )
    if understood and third_person:
        out.append(
            "ACKNOWLEDGE in half a sentence IN YOUR OWN WORDS, addressing the caller in the "
            "SECOND person („Gerai, kad padarėte…“, „Aišku, darote…“) — never quote an "
            "internal summary and never speak about the caller in the third person."
        )
    elif understood:
        out.append(
            f"ACKNOWLEDGE what you understood in half a sentence („{understood}“) — then "
            "continue with one question or step. Address the CALLER („Supratau — …“), never "
            "speak about them in the third person (NOT „Klientas sutinka…“)."
        )
    if u.get("type") == "confusion" and u.get("confusion"):
        out.append(
            f"NOT UNDERSTOOD BY THE CALLER: {u['confusion']} — explain in OTHER, simpler, "
            "everyday words; do not repeat the same sentence."
        )
    return out


# --- identification ----------------------------------------------------------------------


def _identification_notes(state, rt) -> list[str]:
    """Address notes the guards wrote this turn, the encouragement, the phone account, the
    proactive outage and the deterministically heard address parts."""
    s = state
    out: list[str] = []
    if state.turn.address_confirm_note:
        out.append(state.turn.address_confirm_note)
    # The failed lookup's per-level diagnosis: tell the caller what WAS found and ask to
    # correct only the missing part.
    if state.turn.address_lookup_note and not s.identity.customer_id:
        out.append(state.turn.address_lookup_note)
    if (
        not s.identity.customer_id
        and s.intake.problem_type
        and s.dialog.turn_count >= 4
        and not s.identity.profile.street.value
        and not state.identity.address_encouraged
    ):
        state.identity.address_encouraged = True
        out.append(
            "ADDRESS ENCOURAGEMENT (once, warmly): explain WHY you need the address — "
            "without it you cannot see the caller's line or check the fault. Hints: the "
            "contract may be in another family member's name; a street may have been "
            "renamed; the street and house number are enough. Ask what they know."
        )
    if state.closing.wrap_react_note:
        state.closing.wrap_react_note = False
        # What "they paid" means for the service is a business fact, so it is knowledge:
        # the demo says an hour, production says whatever is true — one locale line, no code
        # change (Andrius, 2026-09-23).
        paid = phrase_or("inform.billing_suspended.paid_just_now", "")
        out.append(
            "WRAP-UP PHASE: the business is done but the caller SAID something — react to "
            "THAT specifically: a name → welcome them warmly („Malonu!“); they PAID → "
            f"say exactly this and nothing more about timing: „{paid}“; a "
            "new problem → answer briefly. No long re-explanations. End with „Ar dar kuo "
            "galiu padėti?“."
        )
    if state.turn.reopen_note and not s.identity.customer_id:
        out.append(
            "THE CALLER CORRECTED US: they are calling about a DIFFERENT address than the "
            "one we resolved. Apologise in one sentence and ask for the address they are "
            "calling about (if they already said it — see HEARD ADDRESS and use it). Do not "
            "mention the previous address or its diagnosis again."
        )
    out += _phone_account(state, rt)
    if state.turn.db_address_note and not s.identity.customer_id:
        out.append(state.turn.db_address_note)
    if not s.identity.customer_id:
        from ..identification import extra_questions_guidance

        extra = extra_questions_guidance()
        if extra:
            out.append(extra)
    return out


def _phone_account(state, rt) -> list[str]:
    """The caller's number is in the DB: offer ITS address first — the number is already
    tied to it, so it reveals nothing new and saves the STT-fragile spoken house number.
    Every named part must match (or be unsaid): the same street with a DIFFERENT flat is
    someone else's address (observed: said butas 3, resolved butas 7)."""
    s = state
    from ..identification import offer_phone_address

    def fits(said, mine) -> bool:
        return not said or str(said).lower() == str(mine or "").lower()

    c = s.identity.phone_candidate
    if not (
        offer_phone_address()
        and not s.identity.customer_id
        and c
        and c.get("street")
        # A directive turn owns the moment — the ladder decides WHEN the offer happens.
        and not state.turn.directives.ident
        and not state.turn.directives.ticket
        # The offer comes AFTER the problem and the anamnesis — a garbled first utterance
        # must not trigger it.
        and s.intake.problem_type
        and fits(s.identity.profile.street.value, c.get("street"))
        and fits(s.identity.profile.house.value, c.get("house"))
        and fits(s.identity.profile.apartment.value, c.get("apartment"))
    ):
        return []
    flat = f", butas {c['apartment']}" if c.get("apartment") else ""
    return [
        f"PHONE ACCOUNT: the caller's number is registered at {c['address']}. Offer THIS "
        "address FIRST, before asking them to dictate anything: "
        f"„Ar skambinate dėl {c['street']} {c['house']}{flat}?“. A clean yes identifies them "
        "(the engine looks the address up). If they say a DIFFERENT address (someone "
        "else's — that is allowed), ask them to state the address where the fault is and "
        "take THAT."
    ]


# --- durable case facts --------------------------------------------------------------------


def _case_facts(state, rt) -> list[str]:
    """Identity, problem, ticket, and the closed-case states."""
    s = state
    out: list[str] = []
    if s.identity.customer_id:
        out.append(f"Customer ID: {s.identity.customer_id}")
    if s.identity.customer_name:
        out.append(f"Customer name: {s.identity.customer_name}")
    if s.identity.customer_address:
        out.append(f"Address: {s.identity.customer_address}")
    if s.intake.problem_type:
        out.append(f"Problem type: {s.intake.problem_type}")
    if s.intake.symptoms:
        parts = ", ".join(f"{k}={v}" for k, v in s.intake.symptoms.items())
        out.append(f"SYMPTOMS (the caller's): {parts}.")
    if s.ticket.ticket_id:
        out.append(f"Ticket: {s.ticket.ticket_id}")
    out += _debt_facts(state, rt)
    if s.closing.case_closed and s.closing.is_complete:
        out.append(
            "CALL OVER: the caller said goodbye / has nothing more. Say ONLY one short "
            "farewell („Ačiū, kad paskambinote. Geros dienos!“) and NOTHING else — no new "
            "questions."
        )
    elif s.closing.case_closed:
        out.append(f"CASE CLOSED (reason: {s.closing.closed_reason or 'resolved'}).")
        # An engine-registered ticket (consent-free escalate): ANNOUNCE it — never ask
        # permission or offer to register again.
        if s.closing.closed_reason == "registered" and s.ticket.ticket_id:
            out.append(
                "REGISTERED: the fault is already registered (the engine did it). Say in one "
                "sentence that you registered the fault and colleagues will get in touch and "
                "explain in more detail. Do NOT ask for consent, do NOT offer to register "
                "again, do not read the ticket ID."
            )
        # Just resolved: confirm briefly, then OFFER one more thing and WAIT — the engine
        # ends the call once the caller declines.
        if s.closing.closed_reason == "resolved" and s.resolution.procedure:
            out.append(
                "SOLVED: the caller confirmed the internet works. Be glad briefly and ask "
                "„Ar dar kuo nors galiu padėti?“. Do NOT say goodbye yet, do NOT ask about "
                "equipment, do NOT ask them to check again."
            )
    return out


def _debt_facts(state, rt) -> list[str]:
    """The debt figures of a suspended service are OURS to state — they explain why the
    internet is off (live: „kokia skola?“ got „nematau… buhalterija“). Only billing
    DISPUTES go to customer service."""
    from ..faults import verdict_flag

    net = state.diagnosis.verdicts.get("network") or {}
    if verdict_flag(net.get("reason"), "inform") != "debt":
        return []
    debt = (net.get("signals") or {}).get("billing_debt") or {}
    if not debt.get("amount"):
        return []
    from ..contract.locale import lang

    bits = [f"skola {lang().money(float(debt['amount']))}"]
    months = lang().months(debt.get("months") or [])
    if months:
        bits.append(f"už {months}")
    last_payment = lang().date(debt.get("last_payment"))
    if last_payment:
        bits.append(f"paskutinis mokėjimas gautas {last_payment}")
    return [
        "DEBT FACTS (asked about the sum or the months — SAY these numbers, they are in "
        "your system): "
        + "; ".join(bits)
        + ". After payment the service comes back automatically within an hour. Send them to "
        "customer service ONLY for invoice disputes or a breakdown; never offer to connect "
        "them to any department — you have no such service."
    ]


# --- the dialogue's own state ----------------------------------------------------------------


def _dialogue_state(state, rt) -> list[str]:
    """Stuck ladder, silence, the caller's intent while we wait, plain-words requests."""
    s = state
    out: list[str] = []
    out += _stuck(state, rt)
    # Once stuck AND still unidentified, hand over EVERYTHING the caller said: VAD/STT
    # splits and garbles spoken numbers, and no single turn resolves — the whole buffer
    # lets the model infer the intended address.
    if (
        not s.identity.customer_id
        and s.dialog.stuck_count >= 1
        and len(s.intake.heard_utterances) >= 2
    ):
        recent = " | ".join(s.intake.heard_utterances[-8:])
        out.append(
            f'ALL HEARD (reconcile): the caller has said these pieces so far: "{recent}". '
            "STT may have split or garbled a spoken number („šešiasdešimt“ 60 can arrive as "
            "„šešias dešimt“ and mis-parse to 10). Infer the MOST LIKELY full address from "
            "everything above (prefer the latest correction) and say it back for a yes/no "
            "confirmation — do not make the caller repeat again if you can reasonably infer it."
        )
    if s.diagnosis.outage_reported and not s.closing.case_closed:
        out.append(
            "OUTAGE ANNOUNCED for this street — that IS the final answer. Do NOT ask for the "
            "house or flat, do NOT diagnose, do NOT suggest power or cables. Answer the "
            "caller's questions about the outage (time, progress, compensation). When they "
            "understand / will wait — say goodbye; the engine closes the call."
        )
    out += _awaiting(state, rt)
    if s.dialog.clarity_level == "basic" and not s.closing.case_closed:
        out.append(
            "PLAIN WORDS: the caller said they do not follow technical words. Speak "
            "VISUALLY, no jargon, ONE action at a time. Instead of terms say: routeris = "
            "„dėžutė su lemputėmis“; the WAN/internet socket = „lizdas, į kurį įkištas "
            "kabelis, ateinantis iš sienos, dažnai atskiras ir pažymėtas Internet“; LAN = "
            "„kiti lizdai šalia, į kuriuos jungiami namų įrenginiai“; MAC = „įrenginio "
            "numeris mūsų sistemoje“. Say WHERE to look („routerio galinėje pusėje“), not "
            "only WHAT."
        )
    return out


def _stuck(state, rt) -> list[str]:
    """The caller's last reply did not advance us: acknowledge, narrow, change tactic —
    never loop the same question. The account-code tactic belongs to identification only."""
    s = state
    if s.dialog.stuck_count >= 2 and not s.identity.customer_id:
        return [
            "STUCK: do NOT repeat the same question. Change tactic — offer the account code "
            "(„Gal turite abonento kodą nuo sąskaitos?“) or register the problem for a "
            "call-back."
        ]
    if s.dialog.stuck_count >= 2:
        return [
            "STUCK: do NOT repeat the same question. Rephrase it differently or offer to "
            "register the fault (a technician will get in touch). Do NOT ask for the account "
            "code — the caller is already identified."
        ]
    if s.dialog.stuck_count != 1:
        return []
    extra = (
        " You asked the previous question word for word — you MUST rephrase it."
        if state.dialog.last_reply_repeated
        else ""
    )
    if s.dialog.last_heard:
        # We DID hear them — we just could not use it. Never say „neišgirdau“ here.
        return [
            f"DID NOT UNDERSTAND (but heard!): the caller just said „{s.dialog.last_heard}“ "
            "and it did not give what is needed. Do NOT say „neišgirdau“ — say what you heard "
            "and what was unclear, and ask them to repeat ONLY that part: „Girdžiu „…“, bet "
            "nesupratau gatvės — pakartokite ją, prašau.“ If the caller is actually talking "
            "ABOUT SOMETHING ELSE (asking, clarifying) — answer THAT instead of repeating "
            "your question." + extra
        ]
    # Silence. They may be listening or thinking, so do not apologise at them —
    # „neišgirdau“ after they said nothing reads as if THEY failed.
    return [
        "SILENCE (the caller said nothing): do NOT say „neišgirdau“ — they may just be "
        "listening or thinking. Calmly, without apologising, ask for what is needed (e.g. "
        "the street), or check in with „Ar mane girdite?“. Do not rush." + extra
    ]


def _awaiting(state, rt) -> list[str]:
    """Why the turn did not move us on — so the reply answers what the caller actually did
    instead of re-asking the same sentence."""
    s = state
    if not s.dialog.awaiting or s.closing.case_closed:
        return []
    from ..perceive.detectors import INTENT_CONFUSED, INTENT_IN_PROGRESS, INTENT_QUESTION

    out: list[str] = []
    if s.dialog.last_intent == INTENT_IN_PROGRESS:
        out.append(
            "THE CALLER IS STILL DOING IT: they said they are going / fetching / about to — "
            "it is NOT done yet. Briefly confirm that you will wait („Gerai, palauksiu — "
            "pasakykite, kai būsite pasiruošęs“) and WAIT. Do NOT repeat the instruction, do "
            "NOT assume it failed, do NOT move on."
        )
    elif s.dialog.last_intent == INTENT_QUESTION:
        out.append(
            "THE CALLER ASKED SOMETHING: answer their question simply first, then gently "
            "return to what you asked for. Never repeat your question without answering."
        )
    elif s.dialog.last_intent == INTENT_CONFUSED:
        if s.dialog.step_confusions >= 2:
            out.append(
                "STILL NOT FOLLOWING (2+ times): stop explaining the same thing. Take the "
                "SMALLEST possible piece — one physical action doable in a second („Ar matote "
                "dėžutę su lemputėmis? Tiesiog pasakykite taip ar ne“) — and go one such step "
                "at a time. If that fails too, offer to register a technician visit."
            )
        else:
            out.append(
                "THE CALLER DID NOT FOLLOW: do NOT repeat the same words. Break this step into "
                "a SMALLER one — first lead them to WHERE to look and what it looks like, and "
                "ask for that one thing only."
            )
    if s.dialog.awaiting_turns >= 3:
        out.append(
            "LONG WAIT: several turns without progress. Check in like a human, ask how it is "
            "going and where they are („Ar pavyksta rasti? Gal pasakykite, ką matote“), or "
            "offer to register the fault."
        )
    return out


# --- what we believe and what is settled ------------------------------------------------------


def _caller_pending(state) -> bool:
    """The identification ladder's last rung: the caller-intro question is owed this reply,
    so the deferred check result and the findings stay out of it."""
    return bool(
        state.identity.customer_id
        and state.identity.result_pending
        and not state.identity.caller_name
    )  # --- the one instruction for this reply --------------------------------------------------------


def _plan_goal(state, rt) -> list[str]:
    """The goal directives the rules composed this turn: the identification moment, the
    ticket question, the recap, the findings, the evidence question. Normally exactly one
    of them is set, and it is what this reply must achieve."""
    out: list[str] = []
    out += _goal_secondary_problems(state, rt)
    out += _goal_resync(state, rt)
    out += _goal_caller_intro(state, rt)
    out += _goal_identification(state, rt)
    out += _goal_ticket(state, rt)
    _mark_written_step_said(state)
    out += _asked_how(state, rt)
    out += _goal_recap_and_findings(state, rt)
    return out


def _goal_secondary_problems(state, rt) -> list[str]:
    """Before the goodbye the agent asks back about the OTHER complaints heard mid-call;
    they are already on the ticket."""
    s = state
    if not (s.closing.case_closed and getattr(s.intake, "secondary_problems", None)):
        return []
    rechecks = [x for x in s.intake.secondary_problems if x.get("source") == "dependency"]
    if rechecks and not rechecks[0].get("asked"):
        rechecks[0]["asked"] = True  # one-shot: the caller answers it once
        label = phrase_or(f"service_label.{rechecks[0].get('service')}", "")
        return [
            "PLAN GOAL — RE-CHECK THE SERVICE THEY CALLED ABOUT: the fix was on the "
            f"connection their {rechecks[0].get('service')} depends on. Ask whether "
            f"it works now (e.g. „Ar {label} dabar veikia?“) before saying goodbye."
        ]
    others = [x for x in s.intake.secondary_problems if x.get("source") != "dependency"]
    if not others:
        return []
    topics = "; ".join(f"„{x['text']}“" for x in others)
    return [
        "PLAN GOAL — SECONDARY PROBLEMS (ask before saying goodbye): the caller mentioned "
        f"{topics}. Ask whether it is still relevant; say it was passed to the technician "
        "(already on the registration)."
    ]


def _goal_resync(state, rt) -> list[str]:
    """Return after a detour: re-anchor from the LEDGER, never improvise a fresh diagnostic
    (live: „ar prijungtas prie maitinimo?“ re-asked after a detour while all three facts
    were already established)."""
    if not state.dialog.resync_note:
        return []
    state.dialog.resync_note = False
    established = ""
    if state.diagnosis.evidence:
        from ..evidence import summary_lt

        established = summary_lt(state.diagnosis.evidence)
    return [
        "PLAN GOAL — BACK TO SOLVING (after the detour): in one sentence remind where we "
        + (f"are — established: {established} — " if established else "are ")
        + "and continue from the CURRENT goal below (STILL TO FIND OUT / FINDINGS MOMENT / "
        "ASK NOW). Ask NOTHING again that is already established; if the conclusion is clear "
        "— say it and offer the solution."
    ]


def _goal_caller_intro(state, rt) -> list[str]:
    """The caller just introduced themselves — accept warmly, once."""
    if not state.identity.caller_name_heard:
        return []
    state.identity.caller_name_heard = False
    name = state.identity.caller_name
    if not name or name == "nenurodyta":
        return []
    return [
        f"THE CALLER INTRODUCED THEMSELVES: open with a warm welcome — „Malonu, {name}!“ (or "
        "similar) — and carry on with your thought."
    ]


def _goal_identification(state, rt) -> list[str]:
    """The identification moment: the address offer, the problem gate, the address ask."""
    s = state
    idd = state.turn.directives.ident
    if not idd:
        return []
    out: list[str] = []
    # The opening already said WHEN it broke — the caller must HEAR they were heard, one
    # short acknowledgement before the address ask, never a repeated „kada dingo?“.
    if state.intake.opening_heard_note:
        state.intake.opening_heard_note = False
        when = (
            phrase_or(f"anamnesis.when.{s.intake.anamnesis_when}", s.intake.anamnesis_when)
            if s.intake.anamnesis_when
            else phrase_or(
                f"anamnesis.trigger.{s.intake.anamnesis_trigger}", s.intake.anamnesis_trigger
            )
            if s.intake.anamnesis_trigger
            else ""
        )
        out.append(
            "THE CALLER ALREADY SAID when it broke"
            + (f" („{when}“)" if when else "")
            + " — show in a couple of words that you heard it (e.g. „Aišku — nuo vakar.“), and "
            "do NOT ask when it broke."
        )
    if idd["kind"] == "address_offer":
        # No jump: first a short reaction to what the caller JUST said, then the bridge into
        # the address. The question's core stays word for word — the deterministic confirm
        # guard keys off it.
        problem = phrase_or(f"problem_label.{s.intake.problem_type or ''}", "")
        heard = f" („Suprantu — {problem}.“)" if problem else ""
        out.append(
            "PLAN GOAL — IDENTIFICATION STEP: with the first SHORT sentence show that you "
            f"heard what the caller said{heard}, then bridge — the check needs the address — "
            f"and the question's core WORD FOR WORD: „Ar skambinate dėl {idd['adresas']}?“ Do "
            "not change the address. Whole reply example: „Suprantu — dingo internetas. "
            f"Patikrinsiu liniją — ar skambinate dėl {idd['adresas']}?“"
        )
    elif idd["kind"] == "problem_gate":
        out.append(
            "PLAN GOAL — PROBLEM GATE: the caller has not named a clear problem in OUR area. "
            "YOUR COMPETENCE: you solve ONLY internet and TV technical faults — invoices, "
            "contracts and other matters you do NOT solve, and you say so openly. Find out "
            "whether they have an internet or TV problem. If the topic is not yours (an "
            "invoice, „vaikai neklauso“) — name the boundary politely and ask whether there is "
            "a connection or TV problem. If the caller ASKS something — answer in one sentence "
            "and ask about the problem again. Do NOT ask for the address and check nothing. "
            f"(Backup: „{idd['fallback']}“)"
        )
    else:
        out.append(
            "PLAN GOAL — IDENTIFICATION STEP: explain that a check down to the flat needs the "
            f"address, and ask ONLY for the address. (Backup: „{idd['fallback']}“)"
        )
    return out


def _goal_ticket(state, rt) -> list[str]:
    """The ticket dialogue's question moments — the engine owns the stages and the capture;
    only the WORDING is free."""
    td = state.turn.directives.ticket
    if not td:
        return []
    from ..decide.rules.ticket import ticket_need

    if td["kind"] == "phone_intro":
        if state.resolution.bridge_bound:
            goal = (
                "give the good news — the internet works through the computer for now — and "
                "that you are registering a technician for a new router; ask ONE thing only: "
                "whether the number they are calling from suits for contact"
            )
        else:
            goal = (
                f"tell them this cannot be solved over the phone ({ticket_need(state, rt)}) and "
                "that you are registering a technician; ask ONE thing only: whether the number "
                "they are calling from suits for contact"
            )
    elif td["kind"] == "hours":
        # The LLM echoed the just-captured number back with the „iš kurio skambinate“
        # template — the number is DONE, this turn is hours only.
        goal = (
            "ask ONE thing only: when it is most convenient for the caller to be called. The "
            "number is ALREADY captured — do not mention or ask it again"
        )
    else:
        goal = "ask ONE thing only: whether the number the caller is calling from suits for contact"
    return [
        f"PLAN GOAL — TICKET STEP: {goal}. The registration has NOT happened — say "
        f"„užregistruosiu“, never „užregistravau“. (Backup: „{td['fallback']}“)"
    ]


def _instruction_turn(state) -> bool:
    """Is this turn's own goal something the caller must DO?

    Then the finding shares the reply with an instruction, and the instruction is the part
    that must survive: with the full list of what we checked the reply ran to 291 characters
    and the guard cut the instruction off (voice eval C2, 2026-09-23).
    """
    rule = str((state.turn.plan or {}).get("rule") or "")
    return rule.startswith("case.") and rule not in ("case.escalate", "case.resolved")


def _telling_facts(seen: str, short: bool) -> str:
    """The facts as the finding names them — the two most telling when the reply is shared.

    The last conditions a card names are the ones that decide it ("įrenginys matomas, bet
    srautas nevaikšto"), so a shortened finding keeps the END of the list, not its start.
    """
    parts = [p for p in seen.split(", ") if p]
    if not short or len(parts) <= 2:
        return seen
    return ", ".join(parts[-2:])


def _goal_recap_and_findings(state, rt) -> list[str]:
    """The recap reads the gathered facts back in the speaker's own words; the findings
    moment states what was established, the conclusion and the choice."""
    out: list[str] = []
    rd = state.turn.directives.recap
    if rd:
        out.append(
            f"PLAN GOAL — CHECK BACK: did you understand it right — {rd['faktai']}. End with a "
            "confirming question („ar taip?“)."
        )
    fd = state.turn.directives.findings
    if not fd and state.case.finding:
        # The Case worked out a finding on a turn another rule owned (the name question, the
        # ticket intro). It is said WITH this reply — a caller who hears "telefonu
        # neišspręsime" without knowing what we found has been told nothing (Andrius,
        # 2026-09-23). One line, before this turn's own goal.
        pending = state.case.finding
        state.case.finding = None
        instructing = _instruction_turn(state)
        seen = _telling_facts(pending["faktai"], instructing)
        head = f"{seen} — {pending['isvada']}" if seen else pending["isvada"]
        unchecked = (
            ""
            if instructing or not pending.get("prielaida")
            else f" We could not check this together: {pending['prielaida']}."
        )
        out.append(
            f"PLAN GOAL — OPEN THE REPLY WITH THIS, in ONE short clause, before anything "
            f"else: {head}.{unchecked} Then this turn's own goal — that is the part the "
            f"caller must act on, so it must survive: keep the whole reply to two sentences."
        )
    if fd:
        state.case.finding = None
        # Ticket-first faults script their own offer (`offer_goal` in the pack): the primary
        # outcome first, the convenience as the question.
        if fd.get("offer"):
            solution = f" {fd['offer']}"
        elif fd.get("solutions"):
            solution = f" Offer the choice ({fd['solutions']}) and ask how we proceed."
        else:
            solution = ""
        # The findings turn said „Užregistravau“ while create_ticket was still turns away.
        tense = (
            ""
            if state.ticket.ticket_id
            else " The registration has NOT happened — if you mention it, say "
            "„užregistruosiu“, never „užregistravau“."
        )
        unchecked = (
            f" We could NOT check this together — say so and ask them to correct us if it is "
            f"not so: {fd['prielaida']}."
            if fd.get("prielaida")
            else ""
        )
        # A finding TELLS. The instruction is the next turn's, and the engine has not
        # planned it yet — an agent that asks "ar galėtumėte perkrauti?" here, and only then
        # asks whether they can reach the router, is talking backwards (live 2026-09-23).
        wait = (
            ""
            if (fd.get("offer") or fd.get("solutions") or _instruction_turn(state))
            else " Do NOT ask them to do anything yet and do NOT name the next step — say "
            "what we found and stop."
        )
        instructing = _instruction_turn(state)
        seen = _telling_facts(fd["faktai"], instructing)
        room = (
            " This reply also carries the thing the caller must DO — that part must survive, "
            "so keep the finding to one clause and the whole reply to two sentences."
            if instructing
            else " Two or three sentences, no lists or colons."
        )
        out.append(
            f"PLAN GOAL — FINDINGS MOMENT:{tense} together we established — {seen}. "
            f"Conclusion: {fd['isvada']}.{unchecked}{solution}{wait}{room}"
        )
    return out


def _recall_and_notes(state, rt) -> list[str]:
    """The caller's own earlier words they referenced, and the analyst's advisory notes."""
    from .history import recall_lines

    out: list[str] = []
    recall = recall_lines(state, rt)
    if recall:
        out.append(recall)
    out += _analyst_tone(state)
    return out


def _analyst_tone(state) -> list[str]:
    """The analyst's tone signals: how the caller is doing, never what to do. One-shot —
    the deciding signals were applied by the engine when they arrived."""
    signals = state.voice.analyst_signals
    if not signals:
        return []
    state.voice.analyst_signals = None
    out = []
    for signal in signals:
        quote = f" („{signal['quote']}“)" if signal.get("quote") else ""
        if signal.get("type") == "frustration":
            out.append(
                f"TONE: the caller is losing patience{quote} — acknowledge it plainly, keep "
                "the reply short, and make the next step the smallest possible one."
            )
        elif signal.get("type") == "off_topic":
            out.append(
                f"OFF THE QUESTION: the caller's last words do not answer what you asked{quote} "
                "— answer them briefly, then bring the conversation back to your question."
            )
    return out


def result_narration_tail(state, rt) -> str:
    """The narration directive once the identity has committed and the silent
    diagnose ran. Identification LADDER (2026-07-31): if the caller-intro question
    is still owed (WHO is calling — name + relation, for the record), ask THAT
    first and hold the result one turn (identity.result_pending); otherwise narrate the
    check announce + the REAL result in this one reply (arc v3)."""
    from ..identification import ask_caller, caller_question

    if ask_caller() and not state.identity.caller_name:
        state.identity.result_pending = True
        return (
            " Identifikacijos pabaiga: patikra atlikta TYLIAI, bet rezultato dar "
            f"NESAKYK. Šiame atsakyme TIK: „{caller_question()}“ (galima trumpai "
            "patvirtinti adresą prieš klausimą). Jokio rezultato, jokių instrukcijų."
        )
    d = state.diagnosis.verdicts.get("network") or {}
    gloss = phrase_or(f"verdict.{d.get('reason')}.gloss", d.get("reason") or "—")
    from ...inform import is_news

    if not is_news(d.get("reason")):
        # A fault: the CASE narrates its finding and its step (wave 3). This turn only
        # confirms that the check happened — the walker's own result narration is gone.
        return (
            f" Patikra atlikta. REZULTATAS: {gloss}. Pasakyk jį trumpai ir pereik prie to, "
            "ko reikia toliau (PLAN GOAL). NEkartok adreso klausimo, be instrukcijų sąrašo."
        )
    state.diagnosis.news_delivered = True  # the news goes out in THIS reply — never repeat it
    return (
        f" Patikra atlikta. ŽINIA: {gloss}. Šiame VIENAME atsakyme, šia tvarka: "
        "(1) 'Patikrinsiu būseną šiuo adresu… Patikrinau:' (2) pasakyk žinią "
        "VIENĄ kartą trumpai (jei skola — BŪTINAI pridėk: „apmokėjus sąskaitą, "
        "paslauga bus įjungta“), (3) paklausk „Ar dar kuo galiu padėti?“. "
        "NEkartok adreso klausimo ir daugiau šios žinios NEBEKARTOK."
    )
