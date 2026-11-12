Tu skaitai KLIENTO atsakymą lietuviškame ISP pagalbos skambutyje. STT tekstas gali būti darkytas — spręsk pagal PRASMĘ ir kontekstą, ne pagal raides.
AGENTO PASKUTINIS KLAUSIMAS: „<<anchor>>“
KĄ GEDIMUI REIKIA IŠSIAIŠKINTI: <<needs>>
KAS JAU ŽINOMA: <<ledger>>
Grąžink TIK JSON:
{"facts": {raktas: {"value": reikšmė, "quote": "kliento žodžiai", "hedged": bool}, ...}, "type": "answer|question|deviation|confusion|contradiction", "understood": "puse sakinio kas suprasta", "confusion": "ko klientas nesuprato arba tuščia", "confidence": 0.0-1.0<<step_json>>}
- facts: SURINK VISUS faktus, kuriuos klientas pasakė šiame sakinyje — ir tuos, kurie atsako ne į paskutinį klausimą (klientas dažnai pasako daugiau, nei klausta: „Patikrinau, Wi-Fi įjungtas“ atsakant į „ar galite pasižiūrėti?“ = device_ready: yes IR wifi_on: yes). Galimi TIK šie raktai ir reikšmės:
<<allowed>>
  KIEKVIENAS faktas — atskiras objektas, pvz. „Taip, dabar veikia“: {"restored": {"value": "yes", "quote": "dabar veikia", "hedged": false}}.
  Prie kiekvieno fakto "quote" — TIKSLI kliento žodžių iškarpa (pažodžiui iš jo sakinio), kuri tą faktą pagrindžia; jei negali nurodyti tokios iškarpos, fakto NEDĖK. Rašyk tik tai, ką klientas REALIAI pasakė (tiesiogiai ar iš konteksto: „Radau.“ atsakant į „Radote?“ = device_present: found, quote „Radau“; „ne daganiai viena“ laukiant lempučių = lights: off). Jei klientas fakto nepasakė — rakto NEDĖK; TUŠČIAS facts {} yra normalus ir dažnas atsakymas. „Nežinau“ nėra faktas. PRISKYRIMAS: faktą priskirk tam OBJEKTUI, apie kurį sakinys kalba — „kitas įrenginys nuo rozetės veikia, o routeris ne“ reiškia outlet_works: tried (rozetė veikia!), o NE ką nors apie routerio lemputes; „veikia“ apie kitą prietaisą niekada nereiškia, kad veikia routeris.
  "hedged": true, kai klientas PATS abejoja tuo, ką sako („lyg ir įjungtas“, „turbūt dega“, „rodos, perkroviau“, „gal ir veikia“); kitaip false.
- type: answer (atsako į klausimą, kad ir dalinai — PVZ.: „Galim patikrinti“ = answer-sutikimas; „Dabar esu prie routerio“ = answer; „baltas su antena, keturi lizdai“ atsakant apie routerį = answer); question (klientas KLAUSIA mūsų — sakinyje yra klausimas MUMS, ne šiaip svarstymas); deviation (kalba ne apie gedimą ir neklausia); confusion (sako, kad nesupranta / neranda / nežino kaip); contradiction (paneigia, ką sakė anksčiau pagal KAS JAU ŽINOMA). Abejojant tarp answer ir question — rinkis answer, IŠSKYRUS kai sakinys baigiasi klausimu MUMS (ką / kaip / kur / kada daryti, „…?“) — tada question, net jei prasideda sutikimu.
- understood: trumpa santrauka (lietuviškai), kas suprasta — žurnalui. Jei understood teigia faktą (pvz. „klientas rado routerį“) — tas faktas PRIVALO būti ir facts lauke.
- confusion: pildyk tik kai type=confusion — KO konkrečiai nesuprato.
<<step_rules>>
