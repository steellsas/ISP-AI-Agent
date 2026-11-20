# 9. Dažni klausimai

[← 8. Planas](8-planas.md) · [Turinys](README.md)

---

## Nauda ir kaina

**Kiek sutaupysime?**
Savaitgalio ir vakaro IT support pamaina nebereikalinga. Tikslius skaičius duos pokalbių analizė
(0 etapas) ir pilotas.

**Kiek kainuoja?**
Darbo kaina ir bendradarbiavimo forma aptariamos atskirai. Serverio išlaidos priklauso nuo
talpinimo sprendimo: savas, pirktas ar nuomojamas (orientyras — ~€400/mėn. nuoma). Veikiant jūsų
serveryje, nemokama už kiekvieną skambutį.

**Kada matysime rezultatą?**
Po kiekvieno etapo — tarpinė demonstracija. Pirmasis rezultatas — jūsų skambučių analizė.

**Ar agentas pakeis darbuotojus?**
Pradžioje agentas dirba savaitgaliais ir vakarais. Jis kuriamas taip, kad galėtų dirbti visada,
pvz., kai apkrova didelė ir nespėjama atsiliepti į visus skambučius. Darbuotojai gauna aiškias
žinias ir vėliau — įrankį, kuris padeda aptarnauti.

## Patikimumas

**O jei agentas suklys ar pažadės netiesą?**
Sprendžia taisyklės, ne kalbos modelis. Modelis tik supranta ir kalba, o pažadas be pagrindo
neištariamas. Nežinomas atvejis tampa tiketu žmogui. Kiekvienas skambutis įrašomas ir matomas
stebėsenoje.

**Ką agentas daro, ko nemoka?**
Registruoja tiketą atsakingam skyriui su surinkta informacija ir pasako klientui, kas bus toliau.

**O jei agentas neveikia?**
Skambučiai grįžta į dabartinę PBX tvarką: praleistas skambutis registruojamas, klientui
perskambinama. Tinklo ir serverių prižiūrėtojai gauna įspėjimą.

**Skubus atvejis savaitgalį?**
Agentas neperjungia skambučio žmogui gyvai, o registruoja tiketą atsakingam skyriui. Kas atsakingas
už kurias agento veiklas ir pranešimus, sutariama kūrimo metu.

**Masinė avarija, daug skambučių vienu metu?**
Visi skambinantieji gauna tą pačią informaciją, o tinklo tiketas registruojamas vienas. Kiek
skambučių vienu metu aptarnaujama, išmatuojama serverio etape.

**Ar klientai norės kalbėti su DI?**
Agentas prisistato kaip DI asistentas. Po darbo valandų kita galimybė — neprisiskambinti arba
laukti darbo dienos.

## Technika ir duomenys

**Kodėl ne ChatGPT ar gatavas sprendimas?**
Gatavi sprendimai nežino jūsų tinklo ir negali patikrinti linijos; duomenys keliautų į debesį. Čia
sprendžia jūsų taisyklės ir jūsų sistemų duomenys, o modeliai veikia jūsų serveryje.

**Ar gerai kalba lietuviškai?**
Lietuvių kalba ir atsakymo greitis yra sunkiausios balso agentų vietos. Modeliai parinkti ir
išbandyti lietuvių kalbai, variklis ir paruoštos frazės sumažina klaidų galimybę. Kokybė toliau
gerinama pagal jūsų pokalbius.

**Ar greitai atsako?**
Dabar ~1,5 s. Su GPU serveriu tikslas ~0,6 s.

**Kur saugomi duomenys? BDAR?**
Viskas jūsų serveryje. Įrašų saugojimo terminus nustatote jūs.

**Ar veiks su GPON, DOCSIS, TV?**
Nuo technologijos nepriklausančios dalys (skola, avarija, Wi-Fi, įrenginiai) veikia visiems
klientams iš karto. Technologijos pridedamos palaipsniui pagal jūsų gedimų aprašus.

## Projektas

**Kiek užtruks?**
Apytiksliai ~6 mėnesiai iki piloto. Terminas gali pailgėti, jei vėluos gedimų aprašai, prieigos ar
adapteriai ([8. Planas](8-planas.md)).

**Ko reikės iš mūsų?**
Kuratoriaus iš vadovų, gedimų aprašų iš IT support, prieigų prie sistemų, PBX administratoriaus
pagalbos ir sprendimo dėl serverio ([7. Integracija](7-integracija.md)).

**Kas prižiūrės žinias?**
Pradžioje — Andrius kaip instruktorius. Jis parengia instruktoriaus vadovą ir rolę perduoda įmonės
darbuotojui. Pakeitimus tvirtina kuratorius.

**Ar priklausysime nuo vieno žmogaus?**
Ne. Projekto metu visi darbai perduodami įmonei: kodas, dokumentacija, žinios (failai ir „Gedimų
vadovas“), instruktoriaus vadovas. Vystymą gali perimti kitas darbuotojas.

---

[← 8. Planas](8-planas.md) · [Turinys](README.md)
