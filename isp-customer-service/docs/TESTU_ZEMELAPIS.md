# Testų žemėlapis (sutarta 2026-08-31, peržiūra vyksta pažingsniui)

Tikslas (Andrius): žinoti, kas KĄ tikrina; nebe kurti besidubliuojančių
testų; stambūs pokalbio lygio patikrinimai („supratimas veikia,
identifikacija veikia, tiketas veikia, užbaigimas veikia") + smulkūs vieno
funkcionalumo testai — kiekvienam faktui VIENA vieta.

Būsena peržiūros pradžioje: 37 failai, 933 testai, eval 11 scenarijų (44
čekiai).

## Piramidė ir sluoksnių nuosavybė

| Sluoksnis | Kas garantuojama | Kur gyvena |
|---|---|---|
| EVAL (pokalbio lygis) | pilni pokalbiai: supratimas, identifikacija, sprendimas, tiketas, užbaigimas | `eval/scenarios.json` (S/I serijos) |
| Srauto mechanika | walker/solveris/evidence/direktyvos: žingsnių tvarka, vartai, perdavimai | test_fault_packs, test_resolution, test_evidence, test_dialogue_quality, test_walker_guards, test_router_hung |
| Vieno funkcionalumo unit | detektoriai, verdiktas, adresų resolveris, audio front, adapteriai, įrankiai | test_verdict, test_detectors, test_address_resolver, test_audio_front, test_tools, test_voice_adapters… |

## Taisyklės

1. **Vienas faktas — vienas sluoksnis.** Pvz., identifikacijos atradimo
   variantai (dalimis diktuotas adresas, klaidingas namas, recovery) —
   TIK identifikacijos sluoksnyje (eval I1–I3 + test_address_resolver +
   test_slots). Visuose KITUOSE scenarijuose/testuose identifikacija =
   paruošta būsena (fixture), nebetestuojama pakeliui.
2. **Naujas testas — tik su vieta žemėlapyje.** Jei sluoksnis faktą jau
   dengia — keičiamas esamas testas, ne kuriamas naujas.
3. **Peržiūra vyksta KARTU su pažingsniniu testavimu** (ne atskira
   „didžioji revizija"): testuojame identifikaciją → sutvarkome jos
   sluoksnį; tada analizę/supratimą; tada sprendimo vedimą; tada tiketą ir
   užbaigimą. Kiekvieno etapo išvestis — sluoksnio failų sąrašas šiame
   dokumente + išvalyti dubliai.

## Pažingsninio testavimo eiga (pagal DIALOGO_ETALONAS.md srautą)

| Etapas | Kas tikrinama | Testų sluoksnio failai (pildoma peržiūros metu) |
|---|---|---|
| 1. Prisistatymas + problemos supratimas | greeting, problemos vartai, capture-first | test_nlu, test_understand (dalis), eval |
| 2. Identifikacija | adreso laiptai, resolve, autorizacija, privatumo riba | test_address_resolver, test_slots, test_identification_policy, eval I1–I3 |
| 3. Analizė (telemetrija + hipotezė) | verdiktai, dviejų pusių išvada, fast-path | test_verdict, eval S8 pora |
| 4. Sprendimo vedimas | pack'ai, walker/solveris, turn'o gramatika, verifikacija dviem šaltiniais | test_fault_packs, test_dialogue_quality, test_router_hung, eval S1/S4/S6/S9 |
| 5. Tiketas + užbaigimas | kontaktai, registracija, santrauka, goodbye | test_api (dalis), eval S3 |
| 6. Balso transportas | duplex, delivery, overlay, endpointing | test_audio_front, test_voice_v1, test_overlay_stage2, test_api ws |

## Dubliavimosi kandidatai (tikrinti peržiūros metu)

- `test_agent.py` (131) — istorinis katilas: dalis walker/direktyvų elgsenos
  dabar dengiama test_fault_packs / test_dialogue_quality. Skaidyti pagal
  sluoksnius, dublius naikinti.
- `test_graph.py` (41) — v1 variklio testai; v2 yra numatytasis. Spręsti,
  kiek v1 dar saugome (pariteto kontraktas vs balastas).
- `test_voice_adapters.py` / `test_voice_v1.py` — dalis dengia legacy PART
  kelią; peržiūrėti, kai duplex taps vieninteliu keliu.
