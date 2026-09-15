You read the CALLER's answer while a fault is being registered (the call is in <<language>>; the speech-to-text may be garbled — judge by meaning). AGENT'S QUESTION: "<<anchor>>"
<<task>>
Return JSON only: {"value": ... or null, "type": "answer|question|refusal|other"}
- type=question: the caller ASKS us rather than answers.
- type=refusal: they do not want the registration.
- Invent NOTHING: with no answer, value=null.
