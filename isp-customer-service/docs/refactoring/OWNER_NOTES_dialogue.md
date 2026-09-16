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

## 2. The engine must understand WHAT the caller actually did, not that they "did it"

A caller who runs ahead reports a finished action that was not the action we asked for.

> "Go to the router, we will reboot it — pull the cable." The caller: "I already did,
> rebooted, still no internet." The agent checks HOW: did you pull the power out of the
> wall socket? did you hold it for 5 seconds? The caller: "I just pressed the button."
> The agent goes back to the start of the reboot and leads it step by step.

So a done-report must be VERIFIED against the step's actual requirement before it counts
as the step's answer. Today `procedure.advance` accepts a done-report by intent; the
missing part is the step declaring what makes it done (power out of the socket, held N
seconds) and a clarify question when the report does not match.

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
which check follows it.

---

Status: notes only — nothing here is implemented beyond what M5 already has (the analyst
signals, the check-back on a fact the caller volunteered, the ledger seed from the whole
call). The owner and the executor pick the order after the refactor's mechanical part is
finished.
