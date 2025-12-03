# Internetas Neveikia - Troubleshooting

## Problema
Internetas visiškai neveikia. Jokio ryšio, puslapiai nesikrauna.

## Prioritetas
**AUKŠTAS** - Paslauga visiškai neveikia

## Simptomai
- Nėra interneto jokiame įrenginyje
- Puslapiai nesikrauna (net Google)
- WiFi rodo "Connected, no internet"
- Maršrutizatoriaus Internet/WAN lemputė nedega arba raudona
- Kabeliu prijungus - tas pats

## Greiti Patikrinimai

### 1. Kelių Įrenginių Testas
**Kritinis klausimas:** Ar problema visuose įrenginiuose ar tik viename?

- **Visuose įrenginiuose** → Maršrutizatoriaus/ISP problema
- **Tik viename įrenginyje** → Įrenginio problema (žr. internet_single_device)

### 2. Maršrutizatoriaus Lemputės
**Ką reiškia lemputės:**

| Lemputė | Žalia | Raudona/Oranžinė | Nedega |
|---------|-------|------------------|--------|
| Power | OK | Perkraunamas | Nėra maitinimo |
| Internet/WAN | Yra ryšys | Nėra ryšio | Nėra signalo |
| LAN 1-4 | Prijungtas | - | Neprijungta |
| WiFi | Įjungtas | - | Išjungtas |

### 3. Ar Buvo Pakeitimų?
- Ar kas nors keitė nustatymus?
- Ar buvo elektros dingimas?
- Ar kas nors judino laidus?
- Ar nauji įrenginiai prijungti?

## Troubleshooting Žingsniai

### Žingsnis 1: Maršrutizatoriaus Lemputės
**Tikslas:** Nustatyti maršrutizatoriaus būseną

**Instrukcijos:**
1. Pažiūrėkite į maršrutizatoriaus priekinį skydelį
2. Kokios lemputės dega?
3. Ar kažkuri mirksi?

**Rezultatai pagal lemputę:**
- **Power nedega** → Žingsnis 2 (Maitinimas)
- **Internet/WAN raudona/nedega** → Žingsnis 3 (Kabeliai)
- **Visos žalios** → Žingsnis 4 (Įrenginio problema)

### Žingsnis 2: Maitinimo Patikrinimas
**Jei Power lemputė nedega:**

**Instrukcijos:**
1. Ar maitinimo laidas tvirtai įjungtas į maršrutizatorių?
2. Ar tvirtai įjungtas į rozetę?
3. Pabandykite kitą rozetę
4. Jei yra - pabandykite kitą maitinimo adapterį

**Jei vis tiek nedega:**
- Maršrutizatorius sugedo → Eskalacija (equipment replacement)

### Žingsnis 3: Kabelių Patikrinimas
**Jei Internet/WAN lemputė nedega arba raudona:**

**Instrukcijos:**
1. **WAN kabelis (iš sienos į maršrutizatorių):**
   - Raskite kabelį einantį iš sienos
   - Įjunkite į maršrutizatoriaus WAN portą
   - Ar girdėjote "klik" garsą?
   
2. **Patikrinkite sienos lizdą:**
   - Ar kabelis tvirtai sienos lizde?
   - Ar lizdas nepažeistas?

3. **Perjunkite kabelį:**
   - Ištraukite WAN kabelį
   - Palaukite 10 sekundžių
   - Įjunkite tvirtai atgal

**Po pakeitimo:** Palaukite 1-2 minutes ir stebėkite lemputę

### Žingsnis 4: Maršrutizatoriaus Perkrovimas
**Standartinis reset:**

**Instrukcijos:**
1. Atjunkite maršrutizatoriaus maitinimą
2. **Palaukite 30 sekundžių** (svarbu!)
3. Įjunkite maitinimą atgal
4. Palaukite 2-3 minutes kol užsikraus
5. Stebėkite lemputių seką

**Normali įkrovimo seka:**
1. Power → žalia
2. System mirksi → stabili
3. Internet → žalia (gali užtrukti 1-2 min)
4. WiFi → žalia

**Jei Internet nedega po 3 min:**
- Problema ISP pusėje arba kabelyje → Eskalacija

### Žingsnis 5: WiFi Įrenginio Patikrinimas
**Jei maršrutizatorius OK (visos lemputės žalios):**

**Instrukcijos telefone/kompiuteryje:**
1. Išjunkite WiFi
2. Palaukite 10 sekundžių
3. Įjunkite WiFi
4. Prisijunkite prie tinklo
5. Ar matote "Connected" ar "No Internet"?

**Jei "No Internet" bet Connected:**
- Pabandykite "Forget network" ir prisijungti iš naujo
- Įveskite slaptažodį

### Žingsnis 6: Kabeliu Prijungtas Testas
**Jei WiFi nepadeda:**

**Instrukcijos:**
1. Prijunkite kompiuterį kabeliu tiesiai į maršrutizatorių
2. Naudokite LAN 1, 2, 3 arba 4 portą
3. Ar veikia internetas per kabelį?

**Rezultatai:**
- **Per kabelį veikia** → WiFi problema (channel, slaptažodis)
- **Per kabelį neveikia** → Maršrutizatoriaus/ISP problema

## MCP Diagnostika

### Port Status Check