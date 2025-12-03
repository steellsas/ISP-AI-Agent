flowchart TD
    Start([START]) --> EntryRouter{entry_router}
    
    EntryRouter -->|no messages| Greeting[greeting]
    EntryRouter -->|has messages| ProblemCapture[problem_capture]
    
    Greeting --> END1([END])
    
    ProblemCapture --> PCRouter{problem_capture_router}
    PCRouter -->|waiting| END2([END])
    PCRouter -->|identified| PhoneLookup[phone_lookup]
    
    PhoneLookup --> PLRouter{phone_lookup_router}
    PLRouter -->|1 address| AddressConfirm[address_confirmation]
    PLRouter -->|not found| AddressSearch[address_search]
    
    AddressConfirm --> ACRouter{address_confirmation_router}
    ACRouter -->|confirmed| Diagnostics[diagnostics]
    ACRouter -->|rejected| AddressSearch
    ACRouter -->|waiting| END3([END])
    
    AddressSearch --> ASRouter{address_search_router}
    ASRouter -->|found| Diagnostics
    ASRouter -->|not found| Closing[closing]
    ASRouter -->|waiting| END4([END])
    
    Diagnostics --> DiagRouter{diagnostics_router}
    DiagRouter -->|provider issue| InformIssue[inform_provider_issue]
    DiagRouter -->|client side| Troubleshooting[troubleshooting]
    
    InformIssue --> END5([END])
    
    Troubleshooting --> TSRouter{troubleshooting_router}
    TSRouter -->|escalation| CreateTicket[create_ticket]
    TSRouter -->|resolved| Closing
    TSRouter -->|waiting| END6([END])
    
    CreateTicket --> Closing
    Closing --> END7([END])
```

### 2. **Nodes Reference** - kiekvienas node su:
- Purpose
- LLM Call (Yes/No)
- Input/Output
- Router logic
- State updates
- Code examples

### 3. **Entry Router Logic** - kaip nustatomas entry point

### 4. **Conversation Flow Examples**:
- ✅ Happy Path (problem resolved)
- 🎫 Escalation Path (ticket created)
- ⚠️ Provider Outage Path

### 5. **State Schema** - visi pagrindiniai state fields

### 6. **Language Support** - kaip veikia i18n

### 7. **Edge Cases** - visi aptarti kraštutiniai atvejai

---

## 🎯 Pagrindiniai Flow Paths:
```
HAPPY PATH:
greeting → problem_capture → phone_lookup → address_confirmation 
→ diagnostics → troubleshooting → closing [RESOLVED]

ESCALATION PATH:
... → troubleshooting → create_ticket → closing [TECHNICIAN]

PROVIDER ISSUE PATH:
... → diagnostics → inform_provider_issue → END [OUTAGE]

NOT FOUND PATH:
... → address_search → closing [NOT FOUND]