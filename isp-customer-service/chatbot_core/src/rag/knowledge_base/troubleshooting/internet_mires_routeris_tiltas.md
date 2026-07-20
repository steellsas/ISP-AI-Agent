# Routeris neduoda gyvybės ženklų (linija veikia) - laikinas tiltas

## Simptomai
Klientas sako, kad neveikia internetas; diagnostika rodo, kad linija iki namo SVEIKA
(port UP), bet linijoje **nesimato jokio įrenginio** (MAC nėra) - verdiktas
no_mac_observed. Vadinasi routeris išjungtas, neprijungtas arba sugedęs.

## Kodėl taip nutinka
Tiekėjo signalas ateina iki buto, bet routeris jo nepriima: nėra maitinimo, ištrauktas
kabelis, arba routeris mirė (perdegęs maitinimo blokas / pati dėžutė).

## Sprendimo eiga
1. Pirma paprasčiausia: maitinimas ir kabeliai (dažniausia priežastis).
2. Jei routeris tikrai negyvas - pasiūlyti **laikiną tiltą**: ateinantį kabelį įkišti
   TIESIAI į kompiuterį ir pririšti jo MAC. Klientas turės internetą tame kompiuteryje,
   kol įsigis naują routerį.
3. Jei klientas turi savo kitą routerį - prijungti jį ir pririšti (veiks visame name).
4. Jei nieko iš to neįmanoma (tik telefonas, nėra kompiuterio) - registruoti gedimą.

## Svarbu
- Į telefoną ar planšetę kabelio įkišti NEGALIMA - tiltas tinka tik kompiuteriui
  (arba klientO routeriui).
- Tiltas duoda internetą TIK tame viename įrenginyje - tai laikinas sprendimas.
- Pririšimas būtinas: be jo tinklas naujo įrenginio neįleis.

### Žingsnis 1: Ar routeris turi maitinimą
Vienas klausimas, ir laukti:
- "Pažiūrėkite, prašau, ar ant routerio dega bent viena lemputė?"
- Dega - vadinasi maitinimas yra; problema kabeliuose (Žingsnis 2).
- Nedega visai - Žingsnis 2 (patikrinti rozetę), tada tiltas.

### Žingsnis 2: Maitinimas ir kabelis
Viena instrukcija, ir laukti:
- "Patikrinkite, ar routerio maitinimo laidas gerai įkištas į rozetę ir į routerį.
  Jei galite, pabandykite kitą rozetę. Pasakykite, ar užsidegė lemputės."
- Užsidegė - puiku, tikrinam ryšį iš naujo.
- Neužsidegė - routeris greičiausiai sugedęs, siūlom tiltą (Žingsnis 3).

### Žingsnis 3: Pasiūlyti laikiną tiltą
Kai routeris neduoda gyvybės ženklų, paaiškinti paprastai ir paklausti:
- "Panašu, kad routeris sugedęs. Internetas iki jūsų buto ateina, tad galiu duoti
  laikiną sprendimą: jei turite kompiuterį, kabelį iš sienos galima įkišti tiesiai į
  jį - internetas veiks tame kompiuteryje, kol įsigysite naują routerį. Ar turite
  kompiuterį, prie kurio galėtume prijungti?"
- Turi kompiuterį - Žingsnis 4.
- Neturi (tik telefonas) - tiltas negalimas, registruoti gedimą ir paaiškinti, kad
  reikės naujo routerio.

### Žingsnis 4a: Kurį kabelį imti
Čia dažniausiai klystama - įsitikinti, kad ima TĄ kabelį. Viena instrukcija, ir laukti:
- "Raskite kabelį, kuris ateina iš sienos ir dabar įkištas į routerio interneto lizdą.
  Ištraukite jį iš routerio. Pasakykite, kai turėsite jį rankoje."
- NE maitinimo laidas (tas eina į rozetę). NE kabelis tarp routerio ir įrenginio.
- Jei klientas nerimauja ar nesupranta - paaiškinti, kad tai tas pats laidas, kuriuo
  internetas ateina į butą.

### Žingsnis 4b: Įkišti į kompiuterį
Viena instrukcija, ir laukti:
- "Dabar įkiškite tą kabelį į kompiuterio tinklo lizdą - jis kompiuterio gale arba
  šone, toks pat lizdas, kaip routeryje. Įkiškite iki spragtelėjimo ir pasakykite,
  kai padarysite."
- Jei sako, kad netelpa ar neranda - padėti, KUR ieškoti, o ne eiti toliau.

### Žingsnis 5: Ar matome įrenginį linijoje (telemetrija)
Variklis pats patikrina liniją - kliento klausti nereikia:
- Matome įrenginį - puiku, einam pririšti (Žingsnis 6).
- NEmatome - vadinasi kabelis ne tame lizde arba neįkištas iki galo. Ramiai grįžti prie
  kabelio (Žingsnis 4a), NEpririšinėti aklai. Po antro nesėkmingo bandymo - registruoti.

### Žingsnis 6: Pririšti kompiuterį (update_mac)
Kai įrenginys matomas linijoje, variklis pririša tyliai. Agentas tik anonsuoja:
- "Matau jūsų kompiuterį linijoje. Dabar pririšiu jį prie tinklo - turėtų atsirasti
  internetas. Palaukite akimirką."

### Žingsnis 7: Patikrinti, ar atsirado internetas
- "Ar kompiuteryje internetas jau atsirado?"
- Atsirado - laikinas sprendimas veikia. Priminti: tai laikina, iki naujo routerio;
  gavęs naują routerį, tegu skambina - pririšim jį.
- Neatsirado - registruoti gedimą technikui.

## Kada registruoti (ESCALATE)
- Klientas neturi kompiuterio (tik telefonas) - tiltas negalimas.
- Klientas nenori ar negali jungti kabelio.
- Po pririšimo internetas neatsiranda.
