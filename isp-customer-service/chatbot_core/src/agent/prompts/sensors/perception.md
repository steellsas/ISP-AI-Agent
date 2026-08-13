Tu skaitai KLIENTO atsakymą lietuviškame ISP pagalbos skambutyje. STT tekstas gali būti darkytas — spręsk pagal PRASMĘ ir kontekstą, ne pagal raides.
AGENTO PASKUTINIS KLAUSIMAS: „<<anchor>>“
KĄ GEDIMUI REIKIA IŠSIAIŠKINTI: <<needs>>
KAS JAU ŽINOMA: <<ledger>>
Grąžink TIK JSON:
{"faktai": {raktas: reikšmė, ...}, "tipas": "atsakymas|klausimas|nukrypimas|nesupratimas|prieštaravimas", "supratau": "puse sakinio kas suprasta", "neaiskumas": "ko klientas nesuprato arba tuščia", "pasitikejimas": 0.0-1.0<<step_json>>}
- faktai: TIK šie raktai ir reikšmės: <<allowed>>. Rašyk tik tai, ką klientas REALIAI pasakė (tiesiogiai ar iš konteksto: „Radau.“ atsakant į „Radote?“ = device_present: rado; „ne daganiai viena“ laukiant lempučių = lights: nedega). Jei klientas fakto TIESIOGIAI nepasakė — rakto NEDĖK; TUŠČIAS faktai {} yra normalus ir dažnas atsakymas. Vienoje frazėje beveik niekada nebūna daugiau nei 1–2 faktai.
- tipas: atsakymas (atsako į klausimą, kad ir dalinai — PVZ.: „Galim patikrinti“ = atsakymas-sutikimas; „Dabar esu prie routerio“ = atsakymas; „baltas su antena, keturi lizdai“ atsakant apie routerį = atsakymas); klausimas (klientas KLAUSIA mūsų — sakinyje yra klausimas MUMS, ne šiaip svarstymas); nukrypimas (kalba ne apie gedimą ir neklausia); nesupratimas (sako, kad nesupranta / neranda / nežino kaip); prieštaravimas (paneigia, ką sakė anksčiau pagal KAS JAU ŽINOMA). Abejojant tarp atsakymo ir klausimo — rinkis ATSAKYMĄ.
- supratau: trumpa santrauka agentui atspindėti klientui (lietuviškai). Jei supratau teigia faktą (pvz. „klientas rado routerį“) — tas faktas PRIVALO būti ir faktai lauke.
- neaiskumas: pildyk tik kai tipas=nesupratimas — KO konkrečiai nesuprato.
<<step_rules>>
