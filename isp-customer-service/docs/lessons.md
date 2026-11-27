# Pamokos

> Vieta: `docs/lessons.md`. Čia rašo `/retro`. Kai pamoka pasikartoja 2–3 kartus, ji tampa
> taisykle (`CLAUDE.md`), skill'u arba hook'u. Tada pažymima „→ perkelta į …“.

| Data | Užduotis | Kas nutiko | Pamoka | Perkelta |
|---|---|---|---|---|
| 2026-07-29 | turn-taking | regresiją S4 taisiau kitu būdu nei sutarta | iškilus nesėkmei: sustoti, pateikti variantus | → globalus CLAUDE.md |
| 2026-11-18 | demo worktree | 29 netikri testų kritimai worktree'e | PYTHONPATH Windows forma, DB kopijos | → ISP CLAUDE.md |
| 2026-11-26 | T01 tiketo kontaktai | užduoties taisyklė „pirma `hours_words`“ prieštaravo esamam gyvo skambučio testui `tests/understanding/`; paaiškėjo tik po pilno `pytest` | planuojant ieškoti keičiamos funkcijos (`ticket_capture`) visame `tests/` medyje, ne tik artimiausiame aplanke | |
| 2026-11-26 | T01 tiketo kontaktai | naujas perklausimas neapėmė atsisveikinimo, atsisakymo, klausimo, padėto ragelio, to paties numerio – rado tik `/code-review` | naujam variklio klausimui iš anksto surašyti visas atsakymo rūšis, kurias dialogas jau tvarko, ir kiekvienai testą | |
| 2026-11-27 | T02 testų izoliacija | testas rašė į tikrą `phrases.yaml`, nes `load_locale(root=LOCALES_DIR)` užšaldė kelią ir monkeypatch neveikė; nutrauktas pytest paliko `probe_wave5` | kelius į žinių/frazių failus skaityti kvietimo metu (`root=None` → `root or DIR`, `module.CONST`), testai keičia tik kopiją `tmp_path`; sesijos apsauga `repo_files_unchanged` tai tikrina | |
| 2026-11-27 | T02 testų izoliacija | lygiagrečios užduotys (T01–T04) kiekviena savo šakoje keitė `docs/tasks/README.md` lentelę – konfliktai, T01 retro atkūrė dingusias eilutes (2-as kartas) | užduoties eilutę dėti į `develop` per `/plan-task`, prieš paleidžiant sesiją; užduoties šaka keičia tik savo būseną | → `/plan-task` skill |
| 2026-11-27 | T05 gyvų skambučių patikra | gyvo skambučio scenarijai parašyti iš radinių eilučių: #19 nepasiekė taisyto kelio, #58 trūko vardo perklausimo, #66 ne tas klausimas – 3 iš 6 `/code-review` radinių | gyvo skambučio scenarijų rašyti pagal esamo testo dialogą arba eval stenogramą (tikros variklio frazės ir ėjimų skaičius) | |
| 2026-11-27 | T05 gyvų skambučių patikra | Explore subagentas paleido testus be worktree `PYTHONPATH` ir pranešė 6 netikrus kritimus (2-as kartas po 11-18) | subagento užduotyje nurodyti worktree testų receptą arba uždrausti leisti testus; jo „krenta“ be recepto netikrinti kaip faktą | |
| 2026-11-27 | T05 gyvų skambučių patikra | README užduočių eilutė vėl konfliktavo perkeliant šaką ant `develop` (3-ias kartas) | užduoties eilutė į `develop` prieš paleidžiant sesiją | → `/plan-task` skill |
| 2026-11-27 | T05 gyvų skambučių patikra | eval worktree'e negalimas: nėra `.env`, hook'as jo liesti neleidžia; paleista iš pagrindinio checkout'o (`develop`, švarus) | eval leisti iš pagrindinio checkout'o, kai jis ant `develop` ir švarus | → ISP CLAUDE.md |
