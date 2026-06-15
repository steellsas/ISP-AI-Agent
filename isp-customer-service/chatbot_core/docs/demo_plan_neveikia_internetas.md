# Demo planas — „neveikia internetas"

> **Planavimo dokumentas (demo apimtis).** Čia fiksuojam, ką demo versijoje
> realiai darom, ką imituojam ir kokius scenarijus rodom. Domeno logika
> (priežastys → aptikimas → veiksmas) gyvena atskirame dokumente:
> `scenarijus_neveikia_internetas.md` (šablonas, taikomas ir kitiems gedimams).
>
> Statusas: **PLANAS / DISKUSIJA** — be kodo.

---

## 1. Apimtis ir esmė

- Demo apsiriboja **tik „neveikia internetas / nėra interneto".**
- Tai **galimybių demonstracija**, ne pilnas produktas — visko neatliekam, tik
  parodom, kaip funkcijos veiktų.
- **Įrodom vieną pakartojamą šabloną:**
  **identifikuoja gedimą → randa problemą (verdiktas) → instruktuoja klientą
  pažingsniui → baigia (informuoja / eskaluoja / išsprendžia nuotoliu).**
- Jei tai veikia keliems reprezentatyviems atvejams — visi kiti gedimai
  sprendžiami tuo pačiu principu (tik naujas įrašas/žinių bazės turinys).

---

## 2. Sprendimai (užfiksuoti)

1. **Diagnostikos verdiktas = vienas „storas" deterministinis tool**
   (`diagnose_connection`). Sprendimų medis (§3 domeno dokumente) gyvena kode.
   Grąžina `pusė: tiekėjas / klientas / neaišku` + grupę + veiksmą + signalus.
   - Kai `pusė = klientas` arba `neaišku` → **LLM tęsia pokalbiu** (papildomi
     klausimai + RAG instravimas). Tool **neapsisprendžia už pokalbį.**
2. **SMS — neįtraukiam visai.** Pašalinta iš srauto.
3. **Simuliaciniai (stub) tool'ai** — kelios funkcijos imituojamos (logas +
   „sėkmės" pranešimas), kad parodytume srautą be tikros infrastruktūros.
4. **Kiti veiksmai vėliau** (TR-069 auto-konfig, Wi-Fi slaptažodžio nuskaitymas) —
   tobulinant ir sprendžiant realias problemas.
   **PAKEISTA (2026-06-12): B-Plan grįžta į apimtį** — „tiltas iki techniko":
   kai routeris miręs, bet linija gyva (internetas ateina iki namo, TV irgi
   nerodo): (a) WAN laidas **tiesiai į vieną įrenginį** + MAC pririšimas
   (`update_mac`) → laikinas internetas; (b) klientas pasijungia / nusiperka
   **savo routerį** → pririšame jo MAC → pilna paslauga. Esmė: padėti klientui
   išlaukti techniko. Įgyvendinama per **RAG turinį (6 žingsnis)** + `update_mac`
   stub (5 žingsnis).
5. **Latencijos maskavimas = dviejų greičių srautas** (žr. §4): greiti
   „užbaigiantys" patikrinimai (avarija/skola) — momentiniai; lėta diagnostika —
   su delsimu ir užpildymu pokalbiu.
6. ✅ **PRIVALOMA agento elgsena (į prompt'ą):** lėtame kelyje — „užpildyk
   laukimą simptomų klausimais + lygiagreti diagnostika fone". Ne pasirinktinai —
   įtvirtinta system prompt'e.
7. ✅ **Tiketas = gedimo registracija BE laiko pažado.** Agentas sukuria tiketą
   ir pasako: gedimas užregistruotas, **darbuotojas susisieks** (kitos darbo
   dienos rytą) **ir suderins atvykimo laiką**. Agentas **nežada** konkretaus
   laiko ir nežino meistrų grafikų — gedimą meistrai pasiima pagal galimybes.
   → **Darbo valandų logikos demo'e NĖRA** (jokio „po 18 val." šakojimosi).

---

## 3. Įrankių inventorius (demo)

| Tool | Statusas | Paskirtis |
|---|---|---|
| `find_customer` | yra | Identifikacija (telefonas / adresas) |
| `diagnose_connection` (verdiktas) | **naujas** | Vienu iškvietimu surenka signalus → `pusė/grupė/veiksmas/signalai` iš mock telemetrijos |
| `search_knowledge` (RAG) | yra | Pažingsnis instravimas (B4–B7), po vieną žingsnį |
| `create_ticket` | yra | Reali eskalacija (technikas / įrangos keitimas) |
| `update_mac` / re-auth | **naujas, simuliuotas** | B6 „naujas MAC" — imituotas pririšimas |
| `reset_port` / reboot | **naujas, simuliuotas** | B4 perkrovimas / B3 „port freeze" — imituotas |
| ~~SMS~~ | **išmetam** | — |

### Duomenų šaltinis (kur gyvena telemetrija) — SUTARTA

- **Agentas neliečia DB** — kviečia įrankį (port); už jo adapteris. **Dabar** skaito
  mock seed; **integruojant** kvies realią tinklo sistemą (SNMP / RADIUS / DHCP /
  switch CLI / TR-069 / NMS). Apsikeitimas = **tik adapteris**, agentas ir verdiktas
  nesikeičia. Stabilus seam = **įrankio kontraktas** (`signalai{...}` forma).
- **Telemetrija = tinklo domenas, ne CRM.** Klientas/billing/sutartis → `crm_mcp`;
  switch / port / `observed_mac` / `crc_error_rate` / `dhcp_status` / vlan / avarija →
  `network_mcp`. 3 trūkstami laukai → į `network_schema` (`ports` arba `port_telemetry`);
  `area_outages` gauna `switch_id` FK. **Seed eilutės schemoje**, ne atskiras Python
  mock sluoksnis — viena nuosekli „pasaulio" būsena (Sxx → portai → telemetrija).
- **`diagnose_connection` = orkestratorius** virš abiejų tarnybų: kviečia CRM
  (billing → B1) IR network (switch/port/MAC/CRC/DHCP/avarija → B2–B7), pritaiko
  sprendimų medį. **Nejungiam (JOIN) tarp CRM/network schemų** — kad būsimas atskyrimas
  į dvi realias DB liktų adapterio keitimas, ne perrašymas.
- **Bendra vs atskira DB:** demo'ui fiziškai vienas SQLite failas — gerai (prieiga tik
  per tarnybą). Loginį CRM/network atskyrimą laikom stiprų (atskiros schemos + MCP).

### Verdikto forma (konceptualiai)
```
{
  pusė: "tiekėjas" | "klientas" | "neaišku",
  grupė: "B1".."B7",
  veiksmas: "informuoti" | "kurti_tiketą" | "instruktuoti",
  priežastis: "switch_offline" | "active_outage" | ...,
  signalai: { billing, incident, switch_ping, port_link, kaimynai, mac, crc, dhcp, vlan },
  žinutė_agentui: "trumpas paaiškinimas"
}
```

---

## 4. Latencijos maskavimas (dviejų greičių srautas)

Latenciją slepiam **tik kur jos yra**. Pigūs „užbaigiantys" patikrinimai vykdomi
pirma ir momentiškai; lėta diagnostika — tik jei reikia, su maskavimu.

### Greitas kelias (BE delsimo) — pataikius baigiam iš karto
- **Incidentai / avarija pagal rajoną** (kai adresas žinomas — momentinis lookup).
- (Pasirinktinai) **billing** (skola).
- Jei **B1** (skola) ar **B2** (masinė avarija) → **informuoti iš karto**, baigti.
  Jokio „15–20 s" takto, jokių simptomų klausimų.
- **Operacinė nauda:** masinės avarijos metu daug skambučių vienu metu — kiekvienam
  reikia greitai pasakyti situaciją, negaišinant.

### Lėtas kelias (tik jei greitas praėjo) — su maskavimu
- Pilna diagnostika (switch ping, port status, MAC, CRC, DHCP).
- Taikom: **paskelbk patikrinimą → užpildyk simptomų klausimais** (kada dingo, ar
  judino laidus, ar perkrovė routerį) **→ pateik verdiktą.**
- Simptomų atsakymai dar ir personalizuoja branch B/C formuluotes.

> ✅ **PRIVALOMA (į system prompt'ą):** „užpildyk-laukimą-simptomais +
> lygiagreti diagnostika fone" yra įtvirtinta agento elgsena, ne pasirinktinė.

### Eiliškumo sąlyga
Avarijai patikrinti reikia rajono → **telefonu** rastam klientui adresas žinomas
iškart (greitas kelias veikia). **Adreso** keliu — po hierarchinės paieškos
(žr. `kliento_identifikacijos_dizainas.md`).

### Demo elgsena
- Dirbtinis **~2–3 s delsimas TIK lėtame kelyje** (kad taktas atrodytų realus).
- Greitame kelyje (avarija / skola) — verdiktas **momentinis**.

---

## 5. Demo scenarijai

> Kiekvienas: paleidiklis → verdiktas → pokalbis/veiksmas → pabaiga.
> Grupės ir logika — pagal `scenarijus_neveikia_internetas.md`.

### S1 — Apmokėjimas (B1) · *informacinis, be tiketo*
- **Paleidiklis:** klientas „neveikia internetas".
- **Verdiktas:** `pusė: tiekėjas`, billing = sustabdyta dėl skolos.
- **Veiksmas:** stabdo diagnostiką, informuoja apie skolą/sąskaitą, paaiškina,
  kaip atstatyti paslaugą.
- **Pabaiga:** informacinis. **Tiketo nėra.**

### S2 — Masinė avarija (B2) · *informacinis, be tiketo* — NAUJAS
- **Paleidiklis:** klientas „neveikia internetas"; realiai — perkastas kabelis /
  sugedusi mazgo įranga, be interneto visa gatvė / kvartalas.
- **Verdiktas:** `pusė: tiekėjas`, incident = aktyvi avarija (jau žinoma DB), su ETA.
- **Veiksmas:** stabdo, praneša apie avariją ir numatomą atstatymo laiką (ETA).
- **Pabaiga:** informacinis. **Tiketo NEKURIA** (avarija jau registruota; tai ne
  individualus gedimas). ⟵ **Skirtumas nuo S3.**

### S3 — Tinklo gedimas / individualus (B3) · *eskalacija, tiketas*
- **Paleidiklis:** klientas „neveikia internetas".
- **Verdiktas:** `pusė: tiekėjas`, switch offline ARBA kaimynai DOWN, **bet nėra
  registruotos masinės avarijos** (skiriasi nuo S2).
- **Veiksmas:** praneša apie gedimą, **kuria tiketą** technikui.
- **Pabaiga:** eskalacija (tiketas).

> **S2 vs S3 esmė:** ar gedimas **jau registruotas** kaip incidentas?
> Taip → tik informuoti (B2). Ne, bet aptinkam tiekėjo gedimą → kurti tiketą (B3).

### S4 — Kliento kabelis / maitinimas (B4/B5) · *instravimas → spręsti arba tiketas*
- **Paleidiklis:** klientas „neveikia internetas".
- **Verdiktas:** `pusė: klientas` (arba `neaišku`); port Link DOWN, kaimynai UP →
  lokalu, bet priežastis neatskirta → `veiksmas: instruktuoti`.
- **Pokalbis:** „Ar dega lemputės?" → maitinimas / laido patikra pažingsniui (RAG).
- **Pabaiga:** įsijungė → tikrinam ryšį, **be tiketo**; neįsijungė → **tiketas**.

### S5 — Routerio suderinimas (B6/B7) · *instravimas → spręsti arba tiketas*
- **Paleidiklis:** klientas „neveikia internetas".
- **Verdiktas:** `pusė: klientas`; Link UP + MAC teisingas, bet DHCP nėra užklausų
  (Factory Reset) ARBA matomas svetimas MAC (naujas routeris).
- **Pokalbis/veiksmas:**
  - Naujas MAC → patvirtinus, `update_mac` (simuliuotas) + `reset_port`.
  - Factory Reset → instruktuoja nustatyti DHCP routerio panelėje.
  - (Wi-Fi atšaka: per laidą veikia, Wi-Fi nematyti → įjungti Wi-Fi modulį.)
- **Pabaiga:** išsprendžia nuotoliu; jei per sudėtinga → **tiketas**.

### Filtravimo zona (visiems) · *be tiketo*
- Problema **tik viename įrenginyje** → ne tiekėjo/routerio kaltė → paaiškinti,
  netroubleshootinti, tiketo nekurti.
- **Darbo VPN / trečiųjų šalių PĮ** → nukreipti į įmonės IT, tiketo nekurti.

---

## 6. Scenarijų suvestinė

| # | Scenarijus | Grupė | Pusė | Veiksmas | Tiketas? |
|---|---|---|---|---|---|
| S1 | Apmokėjimas | B1 | tiekėjas | informuoti | ne |
| S2 | Masinė avarija | B2 | tiekėjas | informuoti + ETA | **ne** |
| S3 | Tinklo gedimas (individualus) | B3 | tiekėjas | kurti tiketą | taip |
| S4 | Kabelis / maitinimas | B4/B5 | klientas | instruktuoti | jei nepadeda |
| S5 | Routerio suderinimas | B6/B7 | klientas | instruktuoti / simuliuoti | jei nepadeda |

---

## 7. Atviri klausimai (demo)

- [ ] Ar `diagnose_connection` mock telemetriją vesim per **seed duomenis**
      (kiekvienam scenarijaus klientui — žinoma būsena), ar per atskirą mock sluoksnį?
- [ ] Kurie konkretūs seeded klientai atitiks kiekvieną scenarijų (S1–S5)?
- [ ] Ar reikia papildyti RAG žinių bazę įrašais S4/S5 instravimui?
- [ ] Kokio detalumo simuliuoti `update_mac` / `reset_port` atsakymai (kad pokalbis atrodytų tikras)?
