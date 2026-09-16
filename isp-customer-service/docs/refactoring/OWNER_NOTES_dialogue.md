# Owner's notes — how the dialogue should behave (2026-09-16)

Andrius, while M5 was being built. These are the behaviours the engine must carry; the
wording is polished after the refactor, but the MECHANISMS below are what the remaining
milestones have to make possible. Each note names where it lands today.

## 1. The analyst exists to weigh the context, and the speaker must react to it

When the analyst reports something, the agent may turn on a CLARIFYING question to
settle the doubt — it is not only a tone hint.

> The caller says the lights are on. Later they say one is off, or not lit at all. The
> agent has an ambiguity and must check it back — and, depending on the answer, go back
> to the analysis and redo the hypothesis.

Where it lands: `analyst` signals (M5) → `decide/hypothesis.py` doubt → the confirm
question → `change_confirmed` starts the new cause's procedure. The `contradiction`
signal already does this for a ledger fact; what is missing is the caller-vs-caller case
(they contradict THEMSELVES across turns, with no telemetry involved) and the route back
into a fresh analysis when the confirm lands.

## 2. Clarify when the RESULT is missing — not on every step

The agent works like an engineer with a standard algorithm: it gives the step, and moves
on when the step produced what it should. It does NOT audit how the caller did each
thing, and it does not shadow their every action — a doubting agent is a bad agent.

The clarifying question belongs exactly where the expected result did NOT arrive:

> "Go to the router, we will reboot it." The caller: "I rebooted, still no internet." The
> agent now asks HOW: did you pull the power out of the socket? did you hold it a few
> seconds? — "I just pressed the button." Then the agent leads the reboot properly.

So: reboot worked → carry on, say what it means. Reboot did not work → find out why:
either it was not really done, or the fault is somewhere else. The telemetry read is what
says which of the two it is — it shows whether the device actually went down and came
back, so the agent asks about the how only when the reading and the report disagree.

## 3. Lead the physical work in small steps, and read telemetry between them

> "Pull the cable out of the socket, tell me when it is done." — "done" → the agent
> checks telemetry → "good, I can see it; now plug it back in." — "plugged in" → the
> agent checks telemetry and asks which lights came on, whether the internet light is
> blinking. Telemetry shows the traffic recovering → "I can see traffic now — check
> whether the internet is back."

So a reboot is not one instruction: it is a short loop of instruction → confirmation →
telemetry read → the next instruction, with the agent saying what it sees at each point.

## 4. Say why, and what happens next when it does not work

- Explain WHY a step matters ("we reboot the router because we think it has hung").
- If the caller cannot or will not do it, say plainly why we cannot go further without it.
- Traffic is back but the caller still has no internet → check the other devices; the
  problem may be in the network or in that one device, and solving continues there.
- Traffic did not come back and telemetry says the router is faulty → say it and register
  the fault.
- The network side could not be restored either → register.

## 5. The knowledge is what teaches the agent

How to behave, what to say and how to read the caller belongs in the packs and the
locale, not in code: the step's requirement, its explanation, what each answer means, and
which check follows it. Traffic is back but the caller still has no internet — the pack
says what to try next, and when those are exhausted it is a ticket.

## 6. One conversation engine, many kinds of knowledge

The engine is the part that listens, understands the problem and leads the call; the
knowledge is what it knows about a subject. Today that subject is IT support, but the
same engine should serve other ones — advising on a service or a plan, for instance —
once its knowledge is written.

That splits the work by role, and the architecture has to keep that split honest:
- the INSTRUCTOR fills the knowledge (packs, phrases, what each answer means);
- the DEVELOPER adds tools, and prompts when a new kind of reading is needed;
- the ENGINE stays the same — it does not learn a domain by growing new code paths.

---

Status: notes only — nothing here is implemented beyond what M5 already has (the analyst
signals, the check-back on a fact the caller volunteered, the ledger seed from the whole
call). The owner and the executor pick the order after the refactor's mechanical part is
finished.
