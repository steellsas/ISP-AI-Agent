flowchart TD
    Start([Entry]) --> Greeting[greeting]
    Greeting --> ProblemCapture[problem_capture]
    ProblemCapture --> PhoneLookup[phone_lookup]
    
    PhoneLookup --> CustomerRouter{customer_identification_router}
    CustomerRouter -->|customer_found| AddressConfirm[address_confirmation]
    CustomerRouter -->|not_found| Closing[closing]
    
    AddressConfirm --> AddressRouter{address_confirmation_router}
    AddressRouter -->|confirmed| Diagnostics[diagnostics]
    AddressRouter -->|not_confirmed| Closing
    
    Diagnostics --> DiagRouter{diagnostics_router}
    DiagRouter -->|provider_issue| InformIssue[inform_provider_issue]
    DiagRouter -->|client_side| Closing
    
    InformIssue --> Closing
    
    Closing --> ClosingRouter{closing_router}
    ClosingRouter -->|more_help| ProblemCapture
    ClosingRouter -->|end| End([END])
    
    style CustomerRouter fill:#FFD700
    style AddressRouter fill:#FFD700
    style DiagRouter fill:#FFD700
    style ClosingRouter fill:#FFD700





    """
Updated Flow (Sequential with Background Phone Lookup):

1. greeting → problem_capture

2. problem_capture → [problem_capture_router]
    - If waiting → END
    - If identified → phone_lookup_background

3. phone_lookup_background → [customer_identification_router]
    - Phone: 1 address → address_confirmation
    - Phone: multiple → address_selection
    - Phone: none → address_search

4a. address_confirmation → [address_confirmation_router]
    - YES → diagnostics
    - NO → address_search

4b. address_selection → diagnostics (direct)

4c. address_search → [address_search_router]
    - Found → diagnostics
    - Not found → closing

5. diagnostics → [diagnostics_router]
    - Provider → inform_provider_issue → closing
    - Client → closing

6. closing → [closing_router]
    - More help → problem_capture
    - Done → END
"""
```

---

## 📊 COMPLETE FLOW DIAGRAM
```
START
  ↓
greeting
  ↓
problem_capture
  ├─ waiting → END (pause)
  └─ identified → phone_lookup_background
                    ↓
                  customer_identification_router
                    ├─ 1 address → address_confirmation
                    │                ├─ YES → diagnostics
                    │                └─ NO → address_search
                    │
                    ├─ multiple → address_selection → diagnostics
                    │
                    └─ none → address_search
                                ├─ found → diagnostics
                                └─ not found → closing
                    
diagnostics
  ├─ provider → inform_provider_issue → closing
  └─ client → closing

closing
  ├─ more help → problem_capture (loop)
  └─ done → END