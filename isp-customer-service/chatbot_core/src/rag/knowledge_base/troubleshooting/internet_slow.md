# Lėtas Internetas - Troubleshooting

## Problema
Internetas veikia, bet labai lėtai. Puslapiai kraunasi ilgai, failai atsisiunčiami lėtai.

## Greiti Patikrinmai

### 1. Speedtest
Paprašykite kliento atlikti greitį testą:
- Eikite į www.speedtest.net
- Uždarykite visas kitas programas
- Idealu testuoti per kabelį, ne WiFi
- Normalūs rezultatai: 90-100% plano greičio

### 2. Aktyvios Programos
Dažniausi "greičio valgytojai":
- Netflix, YouTube (4K = 25 Mbps)
- Torrent programos
- Cloud backup (Dropbox, Google Drive)
- Windows Updates
- Video calls (Zoom = 3-5 Mbps)

## Troubleshooting Žingsniai

### Žingsnis 1: WiFi vs Kabelis
**Instrukcijos:**
1. Atlikite speedtest per WiFi
2. Prijunkite kabeliu ir testuokite vėl
3. Palyginkite rezultatus

**Rezultatai:**
- Kabeliu greičiau → WiFi problema
- Abiem lėta → Bendras greičio sutrikimas

### Žingsnis 2: Uždarykite Programas
**Instrukcijos:**
1. Ctrl + Shift + Esc (Task Manager)
2. Performance → Network
3. Processes → rūšiuoti pagal Network
4. Uždarykite programas, kurios naudoja daug

### Žingsnis 3: Per Daug Įrenginių
**Patikrinkite:**
- Kiek įrenginių prijungta?
- Ar kas nors žiūri video?
- Ar kas nors atsisiunčia failus?

**Sprendimas:** Atjunkite nereikalingus įrenginius testavimo metu.

### Žingsnis 4: Maršrutizatoriaus Perkrovimas
**Instrukcijos:**
1. Atjunkite maršrutizatorių 30 sek
2. Vėl įjunkite
3. Palaukite 2-3 minutes
4. Testuokite greitį

### Žingsnis 5: DNS Keitimas
Jei puslapiai kraunasi lėtai bet atsisiuntimai normalūs:
**Google DNS:**
- Preferred: 8.8.8.8
- Alternate: 8.8.4.4

## MCP Diagnostika
```
check_bandwidth_history(customer_id)
```
Patikrina greičio istoriją per 24 val.

**Normalūs rezultatai:**
- Download avg: 90-100% plano
- Upload avg: 90-100% plano
- Maža variacija

**Probleminiai:**
- Avg < 50% plano → Eskalacija
- Didelė variacija → Nestabilus ryšys

## Eskalacija
Sukurti gedimo pranešimą JEI:
- Po troubleshooting problema lieka
- Bandwidth history rodo <70% greičio
- Ping test rodo >5% packet loss

**Prioritetas:** MEDIUM
**SLA:** 24 valandos