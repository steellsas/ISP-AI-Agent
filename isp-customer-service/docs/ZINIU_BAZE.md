# Žinių bazė — kaip įrašyti tai, ką agentas turi žinoti

Nuo 4b bangos (2026-09-23) žinių bazė nebėra „kažkur guli dokumentai": agentas jos klausia
pokalbio metu. Kad surastų **tiksliai tai, ko reikia**, kiekvienas dokumentas pasako, kas jis ir
kaip jį rasti. Nauja žinia = **vienas failas**, jokio kodo.

Vieta: `chatbot_core/src/rag/knowledge_base/<rūšis>/<pavadinimas>.md`

## Antraštė

```yaml
---
title: "TP-Link Archer routeris — lemputės, mygtukai, nustatymai"
kind: equipment            # rūšis (žr. žemiau)
equipment: [tplink]        # kam galioja — iš įrangos katalogo (nebūtina)
problem: [internet_down]   # kokiam skundui (nebūtina)
tags: [router, tplink, lemputes, reset, wps, nustatymai, admin, 192.168.0.1]
---
```

| `kind` | Kam | Pavyzdys |
|---|---|---|
| `equipment` | kas yra įrenginys: lemputės, mygtukai, jungtys | „oranžinė INTERNET = nėra signalo" |
| `howto` | **algoritmas**: kaip ką nors sukonfigūruoti | WAN į DHCP po gamyklinio atstatymo |
| `procedure` | mūsų tvarka | meistro vizitas, įrangos keitimas |
| `troubleshooting` | gedimo kelias | pakibęs routeris, CRC klaidos |
| `faq` | trumpi atsakymai | „ar skambutis kainuoja?" |

**Tagai — tai, ko klientas paklaus jo paties žodžiais.** Rašyk ir be lietuviškų raidžių
(`lemputes` ir `lemputė`): paieška lygina **šaknis** (pirmus 6 ženklus be diakritikų), tad
„sukonfigūruoti" suranda raktą „konfigūravimas", bet „lemp" nesuranda „lampos".

**`equipment` yra apsauga, ne patogumas.** Dokumentas su `equipment: [tplink]` NIEKADA
nepasieks kliento su kita dėžute — nesvarbu, kaip gerai sutampa tagai. Be šios žymės
dokumentas galioja visiems. Žymė turi sutapti su įrangos katalogo lygiu
(`knowledge/v2/equipment/*.yaml`: `tplink`, `router`, `tv_box`, `ont`…).

## Kaip agentas jas naudoja

1. **Atviras klausimas šalia gedimo** („o kiek kainuoja meistras?") — jei nėra tarp penkių
   `knowledge/faq.yaml` temų, atsako dokumentas.
2. **„Kaip…" klausimas pokalbio viduryje** („kaip pakeisti wifi slaptažodį?") — atsakymas
   **tik** iš dokumento, su šaltiniu; neradus — sąžiningai „negaliu patarti", jokių išgalvotų
   registracijų ar terminų.

Radus atsakymą, klientui perskaitomas **skyrius**, ne visas failas — todėl skyrių antraštės
turi būti tikslios („Žingsnis 2: Nustatyti WAN tipą į DHCP", ne „Toliau").

## Patikra

```bash
uv run pytest chatbot_core/tests/test_knowledge_base.py
```

Ten yra lentelė **klausimas → dokumentas**: pridėjęs naują žinią, pridėk ir eilutę su tuo, ko
klientas paklaustų. Jei dokumentas be tagų — testas neleis (niekas jo nesurastų).

Greitis: dokumentai nuskaitomi kartą (~7 ms), viena paieška ~11 ms — balso ėjime nepastebima.

## Algoritmas, per kurį agentas gali VESTI klientą

`kind: howto` dokumentas gali būti ne tik atsakymas, bet ir **kortelės sprendimas**: agentas
duoda po vieną žingsnį per ėjimą ir laukia, kol klientas pasakys, kad padarė.

Kad taip veiktų, žingsniai turi būti **atskiros antraštės**:

```markdown
### Žingsnis 1: Prisijungti prie routerio valdymo skydelio
1. Prijungti kompiuterį ar telefoną prie routerio…
2. Naršyklėje atidaryti 192.168.0.1…

### Žingsnis 2: Nustatyti WAN tipą į DHCP
1. Rasti skiltį „Internet" arba „WAN"…
```

Kortelėje tai viena eilutė (`knowledge/v2/cards/*.yaml`):

```yaml
- module: guide
  args: {knowledge: troubleshooting/internet_factory_reset_dhcp, count: 2}
```

`count` — kiek dokumento žingsnių yra **kliento rankose**. Dokumento „patikrinti" žingsnis
paprastai yra mūsų `verify` (telemetrija — arbitras), tad jo į `count` neįtraukiam.

**Ką tikrina startas:** dokumentas turi egzistuoti ir turėti žingsnių; kitaip programa
nepasileidžia (geriau klaida paleidžiant negu vidury skambučio).

**Vienas žingsnis = vienas atsakymas.** Modulio tikslas nurodo narratoriui sulieti žingsnio
punktus į vieną ar du sakinius ir nedalyti jų per kelis ėjimus — telefonu sąrašo niekas
neatsimena.

## Įrangos lemputės ir spalvos

Įrangos katalogas (`knowledge/v2/equipment/*.yaml`) pasako, ką lemputė REIŠKIA:

```yaml
lights:
  internet:
    ask_key: equipment.tplink.lights.internet
    means:
      green: wan_link=up        # žalia — ryšys yra
      orange: wan_link=down     # oranžinė — įrenginys gyvas, interneto negauna
      red: wan_link=down
      "yes": wan_link=up        # „dega" — kai spalvos nepasakė
      "no": wan_link=down
```

Kortelės apie spalvas nieko nežino — jos kalba tik `wan_link`. Naujam gamintojui reikia tik
jo failo su `means`.

**Nežinomam įrenginiui nespėjama:** bazinis `router.yaml` moka tik tai, kas universalu
(žalia = ryšys, bet kokia deganti spalva = maitinimas yra). Oranžinė ant nežinomos dėžutės
lieka neperskaityta — geriau nežinoti negu pasakyti klientui netiesą.

Spalvą, kurios skaitytuvas nemoka, validatorius atmes paleidimo metu (jis klausia paties
skaitytuvo, kokias spalvas tas moka: `perceive/detectors.LIGHT_COLOURS`).
