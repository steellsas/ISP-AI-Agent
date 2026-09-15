You read the CALLER's reply in an ISP support phone call held in <<language>>. The speech-to-text may be garbled — judge by MEANING and context, not by the letters.
AGENT'S LAST QUESTION: "<<anchor>>"
WHAT THE FAULT STILL NEEDS TO ESTABLISH: <<needs>>
WHAT IS ALREADY KNOWN: <<ledger>>
Return JSON only:
{"facts": {key: value, ...}, "type": "answer|question|deviation|confusion|contradiction", "understood": "half a sentence of what was understood", "confusion": "what the caller did not understand, or empty", "confidence": 0.0-1.0<<step_json>>}
- facts: ONLY these keys and values: <<allowed>>. Write only what the caller REALLY said (directly or from context: <<examples:prompt_perception/from_context>>). If the caller did not DIRECTLY state a fact — leave the key OUT; an EMPTY facts {} is a normal and frequent answer. One phrase almost never carries more than 1–2 facts. ATTRIBUTION: attribute a fact to the OBJECT the sentence talks about — <<examples:prompt_perception/attribution>>.
- type: answer (answers the question, even partly — E.G.: <<examples:prompt_perception/answers>>); question (the caller ASKS us — the sentence holds a question TO US, not just musing); deviation (talks about something other than the fault and does not ask); confusion (says they do not understand / cannot find it / do not know how); contradiction (denies what they said earlier according to WHAT IS ALREADY KNOWN). When unsure between answer and question — choose answer.
- understood: a short summary for the agent to reflect back to the caller (in <<language>>). If understood states a fact (e.g. <<examples:prompt_perception/understood>>) — that fact MUST also be in the facts field.
- confusion: fill only when type=confusion — WHAT exactly they did not understand.
<<step_rules>>
