# Demo Scenarios / Demo Scenarijai

This document contains demo scenarios for ISP customer support agent.
Each scenario is provided in English (EN) and Lithuanian (LT).

---

## Scenario 1: Internet Not Working - Happy Path
## Scenarijus 1: Neveikia internetas - Happy Path

**What it demonstrates / Ką demonstruoja:**
- Full conversation flow / Pilnas pokalbio flow
- Customer identification / Kliento identifikacija
- RAG knowledge search / RAG žinių paieška
- Network diagnostics / Tinklo diagnostika
- Successful resolution / Sėkmingas išsprendimas

### EN Version

```
Agent: Hello! This is TeleCom customer service. How can I help you?
User:  My internet is not working
Agent: [find_customer] 
       I see this number is registered at Vilnius, Gedimino st. 15-3. 
       Are you calling about this address?
User:  Yes
Agent: And what's your name?
User:  Peter
Agent: [search_knowledge: "internet not working"]
       [check_network_status]
       Peter, let's try restarting your router. Unplug it, wait 30 seconds, 
       and plug it back in. Let me know when it's back on.
User:  OK, I'll try... It's working now!
Agent: Great! Is there anything else I can help you with?
User:  No, thank you
Agent: [finish] 
       Thank you for calling TeleCom. Have a great day!
```

### LT Version

```
Agent: Labas! Čia TeleCom klientų aptarnavimas. Kuo galiu padėti?
User:  Neveikia internetas
Agent: [find_customer]
       Matau, šis numeris registruotas adresu Vilnius, Gedimino g. 15-3.
       Ar skambini dėl šio adreso?
User:  Taip
Agent: O kaip tave vadina?
User:  Petras
Agent: [search_knowledge: "internet neveikia"]
       [check_network_status]
       Petrai, pabandyk perkrauti routerį. Išjunk jį iš tinklo, palauk 30 
       sekundžių ir vėl įjunk. Pasakyk kai įsijungs.
User:  Gerai, pabandysiu... Veikia!
Agent: Puiku! Ar dar galiu kuo nors padėti?
User:  Ne, ačiū
Agent: [finish]
       Ačiū, kad skambinai į TeleCom. Geros dienos!
```

---

## Scenario 2: Area Outage
## Scenarijus 2: Gedimas rajone

**What it demonstrates / Ką demonstruoja:**
- Outage detection / Gedimų aptikimas
- Proactive information / Proaktyvi informacija
- No troubleshooting needed / Nereikia troubleshooting

### EN Version

```
Agent: Hello! This is TeleCom customer service. How can I help you?
User:  I don't have internet
Agent: [find_customer]
       I see this number is registered at Kaunas, Laisvės al. 50-12.
       Are you calling about this address?
User:  Yes, I'm Maria
Agent: [check_outages] → OUTAGE FOUND!
       Maria, there's currently network maintenance in your area.
       Estimated restoration time: 6:00 PM. We apologize for the inconvenience.
User:  OK, thanks for letting me know
Agent: You're welcome! Is there anything else?
User:  No
Agent: [finish]
       Thank you for your patience. Have a great day!
```

### LT Version

```
Agent: Labas! Čia TeleCom klientų aptarnavimas. Kuo galiu padėti?
User:  Nėra interneto
Agent: [find_customer]
       Matau, šis numeris registruotas adresu Kaunas, Laisvės al. 50-12.
       Ar skambini dėl šio adreso?
User:  Taip, aš Marija
Agent: [check_outages] → RASTAS GEDIMAS!
       Marija, šiuo metu tavo rajone vyksta tinklo priežiūros darbai.
       Planuojamas atstatymo laikas: 18:00. Atsiprašome už nepatogumus.
User:  Gerai, ačiū kad informavot
Agent: Prašom! Ar dar galiu kuo padėti?
User:  Ne
Agent: [finish]
       Ačiū už kantrybę. Geros dienos!
```

---

## Scenario 3: Slow Internet - Peak Hours
## Scenarijus 3: Lėtas internetas - Piko valandos

**What it demonstrates / Ką demonstruoja:**
- RAG knowledge about peak hours / RAG žinios apie piko valandas
- Diagnostic questions / Diagnostiniai klausimai
- Multiple device check / Kelių įrenginių patikra

### EN Version

```
Agent: Hello! This is TeleCom customer service. How can I help you?
User:  Internet is very slow in the evenings
Agent: [find_customer]
       I see this number is registered at Šiauliai, Tilžės st. 12-5.
       Are you calling about this address?
User:  Yes
Agent: What's your name?
User:  John
Agent: [search_knowledge: "slow internet evening peak"]
       [check_network_status] → All OK
       John, evenings (6-10 PM) are peak hours when many people use the internet,
       so speeds can be lower. Is it slow on all devices or just one?
User:  All devices
Agent: How many devices are connected to your WiFi?
User:  About 8
Agent: That could be part of the issue. Try disconnecting devices you're not using.
       Also, are any devices downloading large files or streaming?
User:  My son might be gaming...
Agent: Online gaming and streaming use a lot of bandwidth. Try pausing those
       activities and test again. Would you like me to check your connection?
User:  OK let me try that first... Yes, it's faster now!
Agent: Great! During peak hours, managing connected devices helps a lot.
       Anything else I can help with?
User:  No, thanks
Agent: [finish]
```

### LT Version

```
Agent: Labas! Čia TeleCom klientų aptarnavimas. Kuo galiu padėti?
User:  Labai lėtas internetas vakarais
Agent: [find_customer]
       Matau, šis numeris registruotas adresu Šiauliai, Tilžės g. 12-5.
       Ar skambini dėl šio adreso?
User:  Taip
Agent: Kaip tave vadina?
User:  Jonas
Agent: [search_knowledge: "lėtas internetas vakaras piko"]
       [check_network_status] → Viskas OK
       Jonai, vakarai (18-22h) yra piko laikas, kai daug žmonių naudojasi 
       internetu, todėl greitis gali būti mažesnis. Ar lėtas visuose 
       įrenginiuose, ar tik viename?
User:  Visuose
Agent: Kiek įrenginių prijungta prie WiFi?
User:  Kokie 8
Agent: Tai gali būti priežastis. Pabandyk atjungti įrenginius, kurių nenaudoji.
       Ar kuris nors įrenginys šiuo metu kažką siunčiasi ar žiūri video?
User:  Sūnus gal žaidžia...
Agent: Žaidimai ir video naudoja daug interneto. Pabandyk sustabdyti tuos
       veiksmus ir patikrink dar kartą. Ar nori, kad patikrinčiau tavo ryšį?
User:  Gerai, pabandysiu pirma... Taip, dabar greičiau!
Agent: Puiku! Piko valandomis svarbu kontroliuoti prijungtų įrenginių skaičių.
       Ar dar galiu kuo padėti?
User:  Ne, ačiū
Agent: [finish]
```

---

## Scenario 4: Escalation - Technician Needed
## Scenarijus 4: Eskalacija - Reikia techniko

**What it demonstrates / Ką demonstruoja:**
- Full troubleshooting attempt / Pilnas troubleshooting bandymas
- Problem not resolved / Problema neišspręsta
- Ticket creation / Užklausos sukūrimas
- Technician scheduling / Techniko registravimas

### EN Version

```
Agent: Hello! This is TeleCom customer service. How can I help you?
User:  Internet hasn't been working for three days
Agent: [find_customer]
       I see this number is registered at Klaipėda, Taikos pr. 77-15.
       Are you calling about this address?
User:  Yes, I'm Andrew
Agent: [search_knowledge: "internet not working"]
       [check_network_status]
       [check_outages] → No outages
       Andrew, I see you've been having issues. Let's try a few things.
       Can you restart your router? Unplug it, wait 30 seconds, plug it back in.
User:  I already tried that, doesn't help
Agent: I understand. Can you check the router lights? What colors do you see?
User:  There's a red light blinking
Agent: [search_knowledge: "router red light blinking"]
       A blinking red light usually indicates a connection problem on our end.
       I'll need to send a technician to check your line.
Agent: [create_ticket]
       I've created a service request #TKT12345. A technician will contact you
       within 24 hours to schedule a visit. Is the phone number ending in 345
       the best way to reach you?
User:  Yes
Agent: Perfect. Is there anything else I can help with?
User:  No, thank you
Agent: [finish]
       Thank you for your patience. The technician will be in touch soon!
```

### LT Version

```
Agent: Labas! Čia TeleCom klientų aptarnavimas. Kuo galiu padėti?
User:  Jau trečią dieną neveikia internetas
Agent: [find_customer]
       Matau, šis numeris registruotas adresu Klaipėda, Taikos pr. 77-15.
       Ar skambini dėl šio adreso?
User:  Taip, aš Andrius
Agent: [search_knowledge: "internet neveikia"]
       [check_network_status]
       [check_outages] → Gedimų nėra
       Andriau, matau kad problemos tęsiasi. Pabandykim kelis dalykus.
       Ar gali perkrauti routerį? Išjunk iš tinklo, palauk 30 sekundžių, įjunk.
User:  Jau bandžiau, nepadeda
Agent: Suprantu. Ar gali patikrinti routerio lemputes? Kokios spalvos dega?
User:  Raudona mirksi
Agent: [search_knowledge: "router raudona lemputė"]
       Mirksinti raudona lemputė dažniausiai rodo ryšio problemą iš mūsų pusės.
       Turėsiu išsiųsti techniką patikrinti tavo liniją.
Agent: [create_ticket]
       Sukūriau užklausą #TKT12345. Technikas susisieks su tavimi per 24 valandas
       ir suderins vizito laiką. Ar telefono numeris, kuris baigiasi 345, yra
       geriausias būdas susisiekti?
User:  Taip
Agent: Puiku. Ar dar galiu kuo padėti?
User:  Ne, ačiū
Agent: [finish]
       Ačiū už kantrybę. Technikas netrukus susisieks!
```

---

## Scenario 5: TV No Signal
## Scenarijus 5: TV nėra signalo

**What it demonstrates / Ką demonstruoja:**
- Non-internet service support / Ne interneto paslaugų palaikymas
- TV troubleshooting / TV problemų sprendimas
- Physical connection check / Fizinio prijungimo patikra

### EN Version

```
Agent: Hello! This is TeleCom customer service. How can I help you?
User:  My TV shows "no signal"
Agent: [find_customer]
       I see this number is registered at Panevėžys, Ramygalos st. 25-8.
       Are you calling about this address?
User:  Yes, I'm Anna
Agent: [search_knowledge: "TV no signal"]
       Anna, let's try a few things. First, can you restart your TV box?
       Unplug it from power, wait 30 seconds, and plug it back in.
User:  OK, let me try... Done, but still no signal
Agent: Can you check if the HDMI cable is properly connected to both the TV
       box and your TV?
User:  Let me check... Oh, it was loose! It's working now!
Agent: Great! Sometimes cables can get loose. Is there anything else I can help with?
User:  No, that's all
Agent: [finish]
       Glad I could help! Have a great day!
```

### LT Version

```
Agent: Labas! Čia TeleCom klientų aptarnavimas. Kuo galiu padėti?
User:  TV rodo "nėra signalo"
Agent: [find_customer]
       Matau, šis numeris registruotas adresu Panevėžys, Ramygalos g. 25-8.
       Ar skambini dėl šio adreso?
User:  Taip, aš Ona
Agent: [search_knowledge: "TV nėra signalo"]
       Ona, pabandykim kelis dalykus. Pirma, ar gali perkrauti TV priedėlį?
       Išjunk jį iš tinklo, palauk 30 sekundžių ir vėl įjunk.
User:  Gerai, pabandysiu... Padariau, bet vis tiek nėra signalo
Agent: Ar gali patikrinti, ar HDMI kabelis gerai prijungtas ir prie priedėlio,
       ir prie televizoriaus?
User:  Patikrinsiu... O, buvo išsijungęs! Dabar veikia!
Agent: Puiku! Kartais kabeliai atsilaisvina. Ar dar galiu kuo padėti?
User:  Ne, viskas
Agent: [finish]
       Džiaugiuosi, kad pavyko padėti! Geros dienos!
```

---

## Testing Checklist / Testavimo checklist

Use this checklist when testing each scenario:
Naudok šį sąrašą testuodamas kiekvieną scenarijų:

- [ ] Greeting displayed / Pasisveikinimas rodomas
- [ ] Customer found correctly / Klientas rastas teisingai
- [ ] Address confirmation asked / Paklaustas adreso patvirtinimas
- [ ] Name asked after address / Vardas paklaustas po adreso
- [ ] RAG search used / RAG paieška panaudota
- [ ] Network check performed / Tinklo patikra atlikta
- [ ] Troubleshooting steps logical / Troubleshooting žingsniai logiški
- [ ] Ticket created when needed / Užklausa sukurta kai reikia
- [ ] Conversation ended properly / Pokalbis baigtas teisingai
- [ ] Informal tone maintained (LT) / Neformalus tonas išlaikytas (LT)

---

## Notes / Pastabos

- Agent may vary responses slightly - that's OK
- Agentas gali šiek tiek varijuoti atsakymus - tai normalu

- Focus on logical flow, not exact wording
- Svarbu logiškas flow, ne tikslus tekstas

- If agent deviates significantly, adjust prompts
- Jei agentas labai nukrypsta, koreguok prompt'us
