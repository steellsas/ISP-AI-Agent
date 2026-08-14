- zingsnis (PRIVALOMAS, nes agentas laukia atsakymo į aktyvų žingsnį): įvertink TĄ PATĮ kliento sakinį kaip atsakymą į žingsnio klausimą.
  Variantai (label: reikšmė):
<<options>>
  {"label": vienas iš variantų arba "unclear", "is_answer": bool, "internally_inconsistent": bool, "confidence": 0.0-1.0}
  - label: rink TIK pagal PRASMĘ (toleruok STT triukšmą). Jei atsakymas neatitinka NĖ VIENOS reikšmės — label="unclear", NEprimesk.
  - is_answer: true jei klientas REALIAI atsakė į šį klausimą — net jei kartu sakė, kad dar bando („gerai, bandau… nė viena lemputė neužsidegė“ YRA atsakymas). false jei dar daro be rezultato, klausia atgal, sako nesuprantąs, arba atsakymas ne apie tai.
  - internally_inconsistent: true jei prieštarauja pats sau viename sakinyje.
  - "unclear" + is_answer=false visada, kai negali užtikrintai priskirti reikšmės.
