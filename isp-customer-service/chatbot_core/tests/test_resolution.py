"""Unit tests for the answer detectors and the routing `Outcome` they produce.

Pure logic — no LLM, no DB. (The v1 strategy sequencer these tests used to share the
file with went with the fault packs.)
"""

from agent.perceive.detectors import detect_conn, detect_scope, detect_yes_no
from agent.resolution import Outcome


class TestDetectYesNo:
    def test_clear_yes(self):
        assert detect_yes_no("taip, prijungiau naują routerį") == Outcome.YES
        assert detect_yes_no("aha, pakeičiau") == Outcome.YES

    def test_denial_wins(self):
        assert detect_yes_no("nieko nekeičiau, nieko nedariau") == Outcome.NO
        assert detect_yes_no("ne") == Outcome.NO
        assert detect_yes_no("routerio nekeičiau") == Outcome.NO

    def test_stt_dropped_i_both_directions(self):
        # STT drops the 'i' in BOTH "keičiau"->"kečiau" (yes) and
        # "nekeičiau"->"nekečiau" (no). The denial must still win.
        from agent.perceive.detectors import confirms_device_change

        assert detect_yes_no("kečiau routerį") == Outcome.YES
        assert confirms_device_change("kečiau routerį") is True
        assert detect_yes_no("nekečiau") == Outcome.NO
        assert detect_yes_no("nieko nekečiau") == Outcome.NO
        assert confirms_device_change("nekečiau") is False

    def test_unclear_is_none(self):
        assert detect_yes_no("nežinau tiksliai kas ten") == Outcome.NO  # nežinau -> denial
        assert detect_yes_no("gerai") is None
        assert detect_yes_no("") is None
        assert detect_yes_no(None) is None


class TestDetectRestored:
    """confirm_restored uses restoration vocabulary (veikia/atsirado/neveikia),
    NOT the device-change words — 'neveikia' must read as NO despite containing
    'veik'."""

    def test_restored_yes(self):
        from agent.perceive.detectors import detect_restored

        assert detect_restored("atsirado internetas") == Outcome.YES
        assert detect_restored("jau veikia") == Outcome.YES
        assert detect_restored("ryšys atsistatė") == Outcome.YES

    def test_restored_no(self):
        from agent.perceive.detectors import detect_restored

        assert detect_restored("vis dar neveikia") == Outcome.NO
        assert detect_restored("nevykia") == Outcome.NO  # STT garble
        assert detect_restored("nėra interneto") == Outcome.NO
        assert detect_restored("ne") == Outcome.NO

    def test_restored_unclear(self):
        from agent.perceive.detectors import detect_restored

        assert detect_restored("hmm") is None
        assert detect_restored("supratau") is None
        assert detect_restored("") is None


class TestClientSideDetectors:
    def test_scope_all_vs_one(self):
        assert detect_scope("visuose neveikia") == "all"
        assert detect_scope("niekur nėra") == "all"
        assert detect_scope("tik telefone") == "phone"
        assert detect_scope("planšetėje neveikia") == "phone"
        assert detect_scope("tik kompiuteryje") == "computer"
        assert detect_scope("nešiojamas neveikia") == "computer"
        assert detect_scope("nežinau") is None

    def test_one_device_unnamed_is_not_guessed(self):
        # "just one" without naming it must NOT be read as a device — guessing once sent
        # a phone user down the cable branch. Phase 3.11: it routes to the explicit
        # WHICH-device step ('one' -> cs_which) instead of holding on None.
        assert detect_scope("tik viename") == "one"
        assert detect_scope("viename įrenginyje") == "one"
        # "nei viename" (= none work = ALL down) must not be misread as one.
        assert detect_scope("nei viename neveikia") == "all"

    def test_tv_needs_a_word_boundary(self):
        assert detect_scope("tik tv") == "phone"
        assert detect_scope("viskas tvarkinga") is None  # "tv" inside a word

    def test_conn_wired_vs_wifi(self):
        assert detect_conn("laidu") == "wired"
        assert detect_conn("kabeliu prijungtas") == "wired"
        assert detect_conn("per wifi") == "wifi"
        assert detect_conn("belaidžiu") == "wifi"
        assert detect_conn("nežinau") is None

    def test_conn_reads_stt_shorthand_and_wireless_devices(self):
        # Observed: "Telefonas prijungtas per WF" fell through -> the agent improvised.
        assert detect_conn("Telefonas prijungtas per WF") == "wifi"
        assert detect_conn("vaifajumi") == "wifi"
        assert detect_conn("planšetėje") == "wifi"  # a phone/tablet can only be wireless


class TestDetectors:
    def test_lights_detector(self):
        from agent.perceive.detectors import detect_lights

        assert detect_lights("nedega") == "no"
        assert detect_lights("dega žalia") == "green"  # wave 4b: the colour is the answer
        assert detect_lights("užsidegė lemputės") == "yes"
        assert detect_lights("nežinau") is None

    def test_have_device_reads_clause_by_clause(self):
        """A computer is what the bridge needs. Observed: "neturiu kito routerio, tik
        kompiuterį turiu" was read as NO (the sentence contains "neturiu"), and the
        agent told the caller internet was impossible with a usable machine to hand."""
        from agent.perceive.detectors import detect_have_device as f

        assert f("Aš neturiu kito routerio, aš tik kompiuterį turiu.") == "yes"
        assert f("turiu kompiuterį") == "yes"
        assert f("atsinešiu kompiuterį") == "yes"
        # genuine no
        assert f("neturiu kompiuterio") == "no"
        assert f("neturiu nieko") == "no"
        assert f("ne, turiu tik telefoną") == "no"  # a phone cannot take a cable

    def test_turn_intent_classifier(self):
        from agent.perceive.detectors import detect_turn_intent as f

        # Only these two may move the walker.
        assert f("mėlyname lizde") == "answer"
        assert f("taip") == "answer"
        assert f("nedega") == "answer"
        assert f("padariau") == "done"
        assert f("įkišau") == "done"
        # These must HOLD it.
        assert f("Gerai, atsinešiu kompiuterį") == "in_progress"
        assert f("tuoj pažiūrėsiu") == "in_progress"
        assert f("o kiek tai kainuos?") == "question"
        assert f("nesuprantu kas tas WAN") == "confused"
        assert f("") == "silence"

    def test_a_done_word_is_seen_even_inside_a_question(self):
        """The intent stays `question` — the caller really did ask something — but the Case
        must still see that the action happened (live 2026-09-28, C1)."""
        from agent.perceive.detectors import detect_turn_intent, says_done_action

        heard = "Tai padariau. Ką tik padariau? Kas toliau?"

        assert detect_turn_intent(heard) == "question"
        assert says_done_action(heard) is True

        # Asking ABOUT the action is not doing it, and neither is a loose "jau"/"viskas".
        assert says_done_action("O ar reikia ištraukti maitinimo laidą?") is False
        assert says_done_action("Ar jau galima?") is False
        assert says_done_action("Ar viskas?") is False

    def test_still_broken_is_an_answer_not_progress(self):
        # "vis dar neveikia" is a real answer to "does it work?" — it must not be read
        # as work in progress, or the verify step would never settle.
        from agent.perceive.detectors import detect_turn_intent

        assert detect_turn_intent("vis dar neveikia") == "answer"

    def test_confusion_detector(self):
        from agent.perceive.detectors import detect_confusion

        assert detect_confusion("nesuprantu kas tas WAN") is True
        assert detect_confusion("neišmanau apie tai") is True
        assert detect_confusion("taip, mėlyname") is False
