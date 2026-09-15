- step (REQUIRED, the agent awaits the answer to the active step): judge THE SAME caller sentence as the answer to the step's question.
  Options (label: meaning):
<<options>>
  {"label": one of the options or "unclear", "is_answer": bool, "internally_inconsistent": bool, "confidence": 0.0-1.0}
  - label: pick ONLY by MEANING (tolerate STT noise). If the answer matches NONE of the meanings — label="unclear", do NOT force a fit.
  - is_answer: true if the caller REALLY answered this question — even if they also said they are still trying (<<examples:prompt_perception_step/still_trying>> IS an answer). false if they are still doing it with no result, ask back, say they do not understand, or the answer is not about this.
  - internally_inconsistent: true if they contradict themselves in one sentence.
  - "unclear" + is_answer=false always, when you cannot confidently assign a meaning.
