# Configuration Documentation

Reference for YAML configuration files.

## Table of Contents

- [Overview](#overview)
- [config.yaml](#configyaml)
- [messages.yaml](#messagesyaml)
- [problem_types.yaml](#problem_typesyaml)
- [troubleshooting_mappings.yaml](#troubleshooting_mappingsyaml)
- [Localization Files](#localization-files)
- [Environment Variables](#environment-variables)

---

## Overview

Configuration is managed through YAML files for easy modification without code changes.

**Location:** `src/config/`

```
src/config/
├── config.yaml                  # General settings
├── messages.yaml                # Response messages
├── problem_types.yaml           # Problem classification
├── troubleshooting_mappings.yaml
└── locales/
    ├── en/
    │   └── messages.yaml
    └── lt/
        └── messages.yaml
```

---

## config.yaml

General application settings.

```yaml
# Application info
app:
  name: "ISP Support Bot"
  version: "2.0"
  default_language: "lt"  # "lt" | "en"
  debug: false

# LLM settings
llm:
  default_provider: "openai"  # | "openai" | "google"
  default_model: "gpt-4o-mini"
  
  # Provider-specific models
  providers:
    openai:
      models:
        - "gpt-4o"
        - "gpt-4o-mini"
    google:
      models:
        - "gemini-1.5-pro"
        - "gemini-1.5-flash"
  
  # Generation settings
  max_tokens: 1000
  temperature: 0.3
  
  # Error handling
  max_retries: 3
  retry_delay: 1.0

# RAG settings
rag:
  enabled: true
  top_k: 5
  similarity_threshold: 0.5
  keyword_weight: 0.3
  
  # Embedding model
  embedding_model: "paraphrase-multilingual-mpnet-base-v2"
  embedding_dim: 768
  
  # Caching
  cache_enabled: true
  cache_size: 1000

# MCP settings
mcp:
  servers:
    crm_service:
      command: "python"
      args: ["-m", "crm_service.src.crm_mcp.server"]
      timeout: 10.0
    
    network_service:
      command: "python"
      args: ["-m", "network_service.src.server"]
      timeout: 5.0

# Conversation settings
conversation:
  max_messages: 50
  session_timeout: 1800  # 30 minutes
  
# Logging
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "logs/chatbot.log"
```

### Accessing Config

```python
from services.config_loader import load_config, get_config_value

# Load entire config
config = load_config()

# Get specific value
model = get_config_value("llm.default_model")
top_k = get_config_value("rag.top_k", default=3)
```

---

## messages.yaml

Response message templates.

```yaml
# Greeting messages
greeting:
  welcome: "Sveiki! Aš esu ISP pagalbos asistentas. Kuo galiu jums padėti?"
  welcome_returning: "Sveiki sugrįžę! Kuo galiu padėti šiandien?"

# Problem capture
problem_capture:
  # Initial acknowledgments by problem type
  acknowledgment:
    internet: "Suprantu, turite interneto problemą."
    tv: "Suprantu, turite televizijos paslaugos problemą."
    phone: "Suprantu, turite telefono ryšio problemą."
    billing: "Suprantu, turite klausimų dėl sąskaitos."
    other: "Suprantu, turite problemą su mūsų paslaugomis."
  
  # Qualifying questions
  questions:
    duration: "Nuo kada pastebėjote šią problemą?"
    scope: "Ar problema visuose įrenginiuose, ar tik viename?"
    tried_restart: "Ar bandėte perkrauti maršrutizatorių?"
    router_lights: "Kokios lemputės šviečia ant maršrutizatoriaus?"
  
  # Transition messages
  proceeding: "Gerai, patikrinkime jūsų paskyrą."
  gathering_info: "Dar keli klausimai, kad geriau suprasčiau situaciją."

# Phone lookup
phone_lookup:
  searching: "Ieškau jūsų paskyros..."
  found: "Radau jūsų paskyrą."
  not_found: "Nepavyko rasti paskyros pagal šį telefono numerį."
  multiple_found: "Radau kelias paskyras, susijusias su šiuo numeriu."

# Address confirmation
address_confirmation:
  confirm_prompt: "Ar teikiate paslaugas adresu {address}?"
  confirmed: "Puiku, patvirtinote adresą."
  wrong_address: "Suprantu, tai ne tas adresas."
  ask_address: "Koks jūsų paslaugų adresas?"

# Diagnostics
diagnostics:
  checking: "Tikrinkime jūsų ryšį..."
  all_ok: "Tinklo diagnostika rodo, kad viskas gerai mūsų pusėje."
  issue_found: "Aptikome problemą mūsų tinkle."

# Provider issues
provider_issue:
  outage: |
    Atsiprašome, bet šiuo metu jūsų rajone yra tinklo sutrikimas.
    Numatomas sutvarkymo laikas: {estimated_fix}.
    Atsiprašome už nepatogumus.
  
  maintenance: |
    Šiuo metu vyksta planiniai techniniai darbai jūsų rajone.
    Darbai turėtų būti baigti: {estimated_fix}.
  
  offer_ticket: "Ar norėtumėte, kad sukurčiau užklausą ir jus informuotume, kai problema bus išspręsta?"

# Troubleshooting
troubleshooting:
  starting: "Gerai, pabandykime išspręsti problemą kartu."
  step_intro: "Kitas žingsnis: {step_title}"
  step_instruction: "{instruction}"
  
  # Help responses
  help_provided: "Štai kaip tai padaryti: {help_text}"
  help_not_available: "Atsiprašau, neturiu papildomos informacijos apie šį žingsnį."
  
  # Progress
  progress: "Puiku! Tęsiame ({current}/{total})."
  almost_done: "Liko tik {remaining} žingsnis(-iai)."
  
  # Outcomes
  resolved: "Puiku! Džiaugiuosi, kad pavyko išspręsti problemą!"
  not_resolved: "Deja, šis žingsnis nepadėjo. Bandykime kitą variantą."
  escalating: "Deja, problemos nepavyko išspręsti nuotoliniu būdu."

# Ticket creation
ticket:
  creating: "Kuriu užklausą..."
  created: "Sukūriau užklausą #{ticket_id}. Mūsų specialistai susisieks su jumis per {response_time}."
  created_technician: "Sukūriau užklausą #{ticket_id} technikui. Jis susisieks su jumis per 24 valandas."

# Closing
closing:
  resolved: "Džiaugiuosi, kad pavyko padėti! Ar galiu dar kuo nors padėti?"
  with_ticket: "Jūsų užklausa #{ticket_id} užregistruota. Ar turite dar klausimų?"
  farewell: "Ačiū, kad kreipėtės! Geros dienos!"
  
# Error messages
errors:
  llm_error: "Atsiprašau, įvyko techninė klaida. Pabandykite dar kartą."
  mcp_error: "Nepavyko pasiekti sistemos. Bandome dar kartą..."
  unknown: "Atsiprašau, kažkas nutiko ne taip. Ar galite pakartoti?"
```

### Accessing Messages

```python
from services.config_loader import get_message, format_message

# Simple message
welcome = get_message("greeting", "welcome")

# Message with parameters
ticket_msg = format_message(
    "ticket", "created",
    ticket_id="TKT-2024-001",
    response_time="24 valandas"
)
```

---

## problem_types.yaml

Problem classification configuration.

```yaml
# Problem type definitions
problem_types:
  internet:
    # Keywords for detection
    keywords:
      - "internetas"
      - "internet"
      - "wifi"
      - "tinklas"
      - "network"
      - "ryšys"
      - "connection"
      - "greitis"
      - "speed"
      - "lėtas"
      - "slow"
      - "neveikia"
      - "not working"
    
    # Context fields to extract
    context_fields:
      duration:
        weight: 25
        question_key: "duration"
        examples: ["nuo vakar", "visą dieną", "ką tik"]
      
      scope:
        weight: 30
        question_key: "scope"
        examples: ["visuose įrenginiuose", "tik telefone", "tik kompiuteryje"]
      
      tried_restart:
        weight: 20
        question_key: "tried_restart"
        type: boolean
      
      router_lights:
        weight: 15
        question_key: "router_lights"
        examples: ["žalios", "raudonos", "nedega"]
      
      connection_pattern:
        weight: 10
        examples: ["nutrūkinėja", "lėtas", "visai nėra"]
    
    # Threshold for proceeding
    context_threshold: 70
    max_questions: 3
    
    # Question priority (ask in this order)
    question_priority:
      - "scope"
      - "duration"
      - "tried_restart"
  
  tv:
    keywords:
      - "televizija"
      - "tv"
      - "televizorius"
      - "kanalai"
      - "channels"
      - "vaizdas"
      - "picture"
      - "signalas"
      - "signal"
    
    context_fields:
      duration:
        weight: 20
        question_key: "duration"
      
      all_channels:
        weight: 30
        question_key: "all_channels"
        type: boolean
      
      decoder_lights:
        weight: 25
        question_key: "decoder_lights"
      
      error_code:
        weight: 25
        question_key: "error_code"
    
    context_threshold: 65
    max_questions: 3
  
  phone:
    keywords:
      - "telefonas"
      - "phone"
      - "skambinti"
      - "call"
      - "numeris"
    
    context_fields:
      issue_type:
        weight: 40
        examples: ["negirdisi", "neskambina", "triukšmas"]
      
      duration:
        weight: 30
      
      all_numbers:
        weight: 30
        type: boolean
    
    context_threshold: 60
    max_questions: 2
  
  billing:
    keywords:
      - "sąskaita"
      - "bill"
      - "mokėjimas"
      - "payment"
      - "kaina"
      - "price"
      - "sutartis"
      - "contract"
    
    context_fields:
      inquiry_type:
        weight: 50
        examples: ["suma", "terminas", "pakeitimas"]
    
    context_threshold: 50
    max_questions: 2
  
  other:
    keywords: []
    context_fields: {}
    context_threshold: 30
    max_questions: 3

# Phrases that indicate user doesn't know answer
skip_phrases:
  - "nežinau"
  - "don't know"
  - "nesuprantu"
  - "neaišku"
  - "not sure"

# Phrases that indicate confusion
unknown_phrases:
  - "kas tai"
  - "what is"
  - "kur"
  - "where"
  - "kaip"
  - "how"
```

### Using Problem Types

```python
from services.config_loader import (
    get_problem_type_config,
    classify_problem_type_by_keywords,
    calculate_context_score,
    get_next_question
)

# Get config for problem type
config = get_problem_type_config("internet")

# Classify by keywords
problem_type = classify_problem_type_by_keywords("neveikia internetas")
# Returns: "internet"

# Calculate context completeness
score = calculate_context_score(
    problem_type="internet",
    context={"duration": "nuo vakar", "scope": "visuose"}
)
# Returns: 55 (out of 100)

# Get next question to ask
question = get_next_question(
    problem_type="internet",
    asked_fields=["duration"],
    context={"duration": "nuo vakar"}
)
# Returns: {"field": "scope", "question": "Ar problema visuose įrenginiuose?"}
```

---

## troubleshooting_mappings.yaml

Maps problem context to scenarios.

```yaml
# Direct mappings (instant routing)
direct_mappings:
  # Single device issues
  single_device:
    conditions:
      scope: ["telefonas", "phone", "vienas", "one", "tik"]
    scenario: "internet_single_device"
  
  # Intermittent connection
  intermittent:
    conditions:
      connection_pattern: ["nutrūksta", "kartais", "intermittent", "drops"]
    scenario: "internet_intermittent"
  
  # Slow connection
  slow:
    conditions:
      connection_pattern: ["lėtas", "slow", "greitis", "speed"]
    scenario: "internet_slow"

# Default scenarios by problem type
defaults:
  internet: "internet_no_connection"
  tv: "tv_no_signal"
  phone: "phone_no_dial_tone"
  billing: null  # No troubleshooting, transfer to billing
  other: null

# Skip step conditions
step_skip_rules:
  # Skip restart if already tried
  router_restart:
    skip_if:
      tried_restart: true
  
  # Skip light check if already reported
  router_lights:
    skip_if:
      router_lights: ["žalios", "green", "all on"]
```

---

## Localization Files

### Structure

```
src/config/locales/
├── en/
│   └── messages.yaml
└── lt/
    └── messages.yaml
```

### lt/messages.yaml (Lithuanian)

```yaml
# Lithuanian messages
greeting:
  welcome: "Sveiki! Aš esu ISP pagalbos asistentas. Kuo galiu jums padėti?"

problem_capture:
  acknowledgment:
    internet: "Suprantu, turite interneto problemą."
    tv: "Suprantu, turite televizijos paslaugos problemą."
  
  questions:
    duration: "Nuo kada pastebėjote šią problemą?"
    scope: "Ar problema visuose įrenginiuose, ar tik viename?"

# ... more Lithuanian translations
```

### en/messages.yaml (English)

```yaml
# English messages
greeting:
  welcome: "Hello! I'm the ISP support assistant. How can I help you?"

problem_capture:
  acknowledgment:
    internet: "I understand you're having an internet problem."
    tv: "I understand you're having a TV service problem."
  
  questions:
    duration: "When did you first notice this problem?"
    scope: "Is the problem on all devices or just one?"

# ... more English translations
```

### Using Translations

```python
from services.language_service import get_language_service

lang_service = get_language_service()

# Set language
lang_service.set_language("en")

# Get translated message
message = lang_service.get_message("greeting", "welcome")
# Returns: "Hello! I'm the ISP support assistant..."
```

---

## Environment Variables

### Required Variables

```bash
# .env file

# LLM API Keys (at least one required)
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...

# Database
DATABASE_PATH=./database/isp_database.db

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/chatbot.log
```

### Optional Variables

```bash

# RAG Settings
RAG_KNOWLEDGE_BASE_PATH=./knowledge_base
RAG_INDEX_PATH=./data/faiss_index

# MCP Settings
MCP_CRM_SERVER_PATH=./crm_service
MCP_TIMEOUT=10

# UI Settings
STREAMLIT_SERVER_PORT=8501
```

### Loading Environment

```python
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
db_path = os.getenv("DATABASE_PATH", "./database/isp_database.db")
```

---
