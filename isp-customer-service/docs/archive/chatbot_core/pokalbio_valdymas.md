# Pokalbio valdymas (turn-taking, pertraukimai, laukimai)

> Bendros agento elgsenos taisyklės balso pokalbiui. **Taikoma visiems
> scenarijams** (ne tik „neveikia internetas"). Liečia ir system prompt'ą, ir
> runtime (endpointing, barge-in, taimautai).
>
> Susiję: latencijos maskavimas — `demo_plan_neveikia_internetas.md` §4 (tas pats
> pokalbio ritmo klausimas).
>
> Statusas: **SUTARTA** — detalės (laiko ribos) tikslinamos.

---

## 1. Pertraukimai ir patikslinimai (barge-in)

- **Leisti klientui baigti (endpointing):** agentas nekerta per vidurį — laukia
  natūralios pauzės. Kai klientas tikėtinai galvoja/tikrina (skaito lipduką ant
  routerio, žiūri laidus) → **ilgesnė tylos riba**, kad nepradėtų kalbėti per anksti.
- **Barge-in:** jei klientas prabyla agentui kalbant → agentas **nutyla ir
  klauso**, neperšaukia.
- **Korekcija / patikslinimas:** jei klientas pataiso („ne penktas, šeštas butas")
  → agentas **atnaujina tą slotą ir atkartoja patvirtinimui**, neignoruoja.
- **Naują info įtraukti į esamą žingsnį**, ne mesti ir neperklausinėti viso.

---

## 2. Laukimai veiksmų metu (reboot ir pan.)

- Kai agentas liepia veiksmą su **realiu laukimu** („perkraukite, po minutės
  pažiūrėsim", „palaukite 30 sek.") → sesija privalo **likti gyva**, jokio
  „laikas baigiasi" pranešimo.
- **Valdyti laukimą aktyviai, perduoti kontrolę klientui:**
  > „Gerai, perkraukite — aš palauksiu. Pasakykite, kai lemputės užsidegs."
  Laukiam **kliento signalo**, ne skaičiuojam atgal.
- Po numatyto intervalo agentas **pats švelniai paklausia** („Ar jau užsidegė
  lemputės?"), o ne nutraukia pokalbį.
- Tai galioja visai sprendimo eigai — kol vyksta troubleshooting'as, laikas
  „nesibaigia".

---

## 3. „State-aware" taimautai (esmė)

- Atskirti **neaktyvumą (tyla)** nuo **maksimalios pokalbio trukmės**.
- Taimauto riba **priklauso nuo pokalbio būsenos:**
  | Būsena | Tylos riba | Pastaba |
  |---|---|---|
  | Identifikacija / rinkimas | trumpa–vidutinė | įprastas turn-taking |
  | Diagnozė (fone) | vidutinė | užpildoma simptomų klausimais |
  | **Laukiam kliento veiksmo** (reboot, laidų tikra) | **pailginta** | tyla = tikėtina, ne neaktyvumas |
  | Sprendimas / pabaiga | trumpa | |
- **Laukimo būsenoje tyla ≠ neaktyvumas** → riba pailginama (numatomas veiksmo
  laikas + buferis).
- „Baigiasi laikas" — tik kai **tikrai** neaktyvu IR nėra aktyvaus veiksmo eigos.

---

## 4. Atviri klausimai

- [ ] Konkrečios laiko ribos kiekvienai būsenai (rinkimas / diagnozė / reboot-wait / idle).
- [ ] Ar demo runtime palaiko barge-in ir state-aware endpointing, ar dalį imituojam?
- [ ] Kaip atpažinti „kliento veiksmo laukimo" būseną (agento intencija → runtime signalas).
