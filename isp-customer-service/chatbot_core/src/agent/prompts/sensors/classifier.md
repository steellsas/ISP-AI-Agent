You read a caller's reply in an ISP phone support call held in <<language>>. The agent asked a question; pick which option MATCHES the caller's answer and whether they actually ANSWERED. The options (label: meaning):
<<options>>
Reply with JSON only:
{"label": one of the labels above or "unclear", "is_answer": bool, "internally_inconsistent": bool, "confidence": 0.0-1.0}
- label: choose ONLY by MEANING (judge meaning, not keywords; tolerate speech-to-text noise). If the reply matches NONE of the meanings, label='unclear' — do NOT force a fit (e.g. <<examples:prompt_classifier/not_lights>> is NOT a lights answer → unclear).
- is_answer: true if the caller actually answered THIS question — even if they also said they were about to try (<<examples:prompt_classifier/still_trying>> IS an answer). false if they are still doing it with no result, asked a question back, said they do not understand, or the reply does not address the question.
- internally_inconsistent: true if they contradict themselves in one sentence.
- 'unclear' + is_answer=false whenever you cannot confidently match a meaning.
