- status (PRIVALOMAS, nes agentas laukia atsakymo į aktyvų žingsnį): KĄ klientas padarė su agento klausimu ar nurodymu. Reikšmė (ką atsakė) čia NEDEDAMA — ji eina į facts.
  Žingsnio klausimas laukia vieno iš šių atsakymų:
<<options>>
  Būsenos (rink VIENĄ — pagrindinę):
    - "answered": atsakė arba pranešė rezultatą („taip, galiu“, „dega žalia“, „perkroviau“, „patikrinau, Wi-Fi įjungtas“). Jei atsakymas turi reikšmę — ją įrašyk į facts.
    - "doing": girdi ir daro, bet rezultato dar nesako („mhm“, „gerai“, „įjungiu“, „palaukit, einu“, „dabar žiūriu“).
    - "asks_back": nežino KAIP ar KUR, klausia, nesuprato („o kur tas mygtukas?“, „kaip tai padaryti?“, „nesupratau“).
    - "pushback": abejoja PRASME, bet neatsisako („o kam to reikia?“, „vakar jau tikrinom“).
    - "not_now": negali DABAR („nesu namuose“, „grįšiu vakare“).
    - "refuses": nenori ar negali daryti apskritai („nedarysiu“, „atsiųskit meistrą“).
    - "off_topic": kalba apie visai ką kita.
  Jei sakinyje yra ir faktas, ir klausimas („Wi-Fi įjungiau, bet kur slaptažodis?“) — faktą VIS TIEK įrašyk į facts, o status rink pagal tai, ko klientas dabar nori (čia "asks_back").
  „Nežinau“ nėra „ne“: fakto nedėk, status "asks_back".
