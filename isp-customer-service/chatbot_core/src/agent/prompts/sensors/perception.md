Tu skaitai KLIENTO atsakymą lietuviškame ISP pagalbos skambutyje. STT tekstas gali būti darkytas — spręsk pagal PRASMĘ ir kontekstą, ne pagal raides.
AGENTO PASKUTINIS KLAUSIMAS: „<<anchor>>“
KĄ GEDIMUI REIKIA IŠSIAIŠKINTI: <<needs>>
KAS JAU ŽINOMA: <<ledger>>
Grąžink TIK JSON:
{"facts": {raktas: reikšmė, ...}, "type": "answer|question|deviation|confusion|contradiction", "understood": "puse sakinio kas suprasta", "confusion": "ko klientas nesuprato arba tuščia", "confidence": 0.0-1.0<<step_json>>}
- facts: TIK šie raktai ir reikšmės: <<allowed>>. Rašyk tik tai, ką klientas REALIAI pasakė (tiesiogiai ar iš konteksto: „Radau.“ atsakant į „Radote?“ = device_present: found; „ne daganiai viena“ laukiant lempučių = lights: off). Jei klientas fakto TIESIOGIAI nepasakė — rakto NEDĖK; TUŠČIAS facts {} yra normalus ir dažnas atsakymas. Vienoje frazėje beveik niekada nebūna daugiau nei 1–2 faktai. PRISKYRIMAS: faktą priskirk tam OBJEKTUI, apie kurį sakinys kalba — „kitas įrenginys nuo rozetės veikia, o routeris ne“ reiškia outlet_works: tried (rozetė veikia!), o NE ką nors apie routerio lemputes; „veikia“ apie kitą prietaisą niekada nereiškia, kad veikia routeris.
- type: answer (atsako į klausimą, kad ir dalinai — PVZ.: „Galim patikrinti“ = answer-sutikimas; „Dabar esu prie routerio“ = answer; „baltas su antena, keturi lizdai“ atsakant apie routerį = answer); question (klientas KLAUSIA mūsų — sakinyje yra klausimas MUMS, ne šiaip svarstymas); deviation (kalba ne apie gedimą ir neklausia); confusion (sako, kad nesupranta / neranda / nežino kaip); contradiction (paneigia, ką sakė anksčiau pagal KAS JAU ŽINOMA). Abejojant tarp answer ir question — rinkis answer.
- understood: trumpa santrauka agentui atspindėti klientui (lietuviškai). Jei understood teigia faktą (pvz. „klientas rado routerį“) — tas faktas PRIVALO būti ir facts lauke.
- confusion: pildyk tik kai type=confusion — KO konkrečiai nesuprato.
<<step_rules>>
