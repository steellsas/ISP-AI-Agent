# Pokalbis po priežasties (skola)

Andrius, 2026-10-30. Kaip agentas kalba, kai jau žino, kodėl neveikia paslauga.

## Principas

Agentas pasako priežastį ir ją aiškina iš faktų. Ko atsakyti negali, pasiūlo perduoti
atsakingam asmeniui ir pasako, į ką tas atsakys. Jei klientas ginčija skolą, agentas surenka jo
argumentus (kada, kokiu būdu, kokią sumą mokėjo) ir perduoda juos buhalterijai. Pokalbis
nenutrūksta, kai baigiasi bandymai.

## Eiga

```
Agentas: priežastis (skola 49,98 € už liepą–rugpjūtį, paskutinis mokėjimas birželio 5 d.)
   │
   ├─ „Gerai, ačiū" / „Ne" ─────────────────────────────► atsisveikina
   │
   ├─ tikslinasi („kiek?", „kada paskutinis?") ─────────► atsako iš faktų
   │
   ├─ „Aš mokėjau" / „Liepą 40 eur" ─► klausia, ko trūksta:
   │      „Kad atsakingas asmuo galėtų rasti jūsų mokėjimą, pasakykite —
   │       kada mokėjote, kokią sumą ir kokiu būdu?"   (≤ 2 kartus)
   │                    │
   ├─ „Nesutinku" ──────┤
   │                    ▼
   │   „Ačiū. Sistemoje matau skolą … Jūsų nurodyto mokėjimo (liepos mėn., banko
   │    pavedimu, 40 €) sistemoje nematau. Galiu perduoti jūsų klausimą atsakingam
   │    asmeniui — jis paieškos mokėjimo pagal šiuos duomenis. Ar registruoti?"
   │                    │
   │     taip / „pasižiūrėkit" ──► kontaktas → tiketas buhalterijai
   │     klausimas („kodėl nematot?") ──► faktai + „Į tai atsakyti negaliu … Ar registruoti?"
   │     neaišku ──► klausia dar kartą (niekada nelaikoma „ne")
   │     ne ──► „Gerai, neregistruoju. Ar dar kuo galiu padėti?"
   │
   └─ „Užregistruokit", „sujunkite" (bet kada) ─► pasiūlymas / registracija variklyje
```

Po pasiūlymo ribos (2 LLM reakcijos) agentas klausia „Ar dar kuo galiu padėti?“, o ne
atsisveikina. Skambutį baigia kliento „ne“ arba atsisveikinimas, arba tyla.

## Tiketas buhalterijai

```
Skolos ginčas. Klientas atjungtas už skolą 49 eurai 98 centai už liepą ir rugpjūtį.
Sistemoje paskutinis mokėjimas — birželio 5 d. Kliento teiginys: mokėjo liepos mėn.,
banko pavedimu, 40 €; sistemoje šio mokėjimo nematyti. Kliento klausimai: O kodėl jūs
nematote mano mokėjimo? Kontaktas: Tomas, tel. +37060020101, skambinti: bet kada.
```

## Kur kode

| Kas | Kur |
|---|---|
| Ginčo eiga | `decide/rules/requests.py` `debt_offer_turn` |
| Variklio žodžiai | `decide/rules/reply.py` `_debt_words`; frazės `identification.debt_*` |
| Mokėjimo teiginys | `perceive/payment_claim.py`; žodynas `payment_*` |
| Tiketas | `executor_flow.py` `_debt_dispute_details`; frazės `ticket.details.debt_*` |
| Ribos | `limits.yaml` `debt_claim_asks_max` |

## Testai

`tests/ticket/test_requests.py::TestDebtDispute`,
`tests/closing/test_phase.py::test_a_disputed_payment_goes_to_the_accounting_with_its_details`,
`test_the_call_is_not_ended_while_the_caller_talks`.
