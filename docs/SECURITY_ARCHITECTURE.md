# Architecture

```mermaid
flowchart LR
  subgraph LOCAL[Local Windows machine]
    UI[React UI]
    API[FastAPI loopback API]
    DB[(SQLite)]
    FILES[Excel and backups]
    KEYS[Windows Credential Manager]
    PDF[PDF child process: 512 MiB / 20 s]
    OLLAMA[Optional loopback Ollama]
    UI -->|Host / Origin / cross-site guard| API
    API --> DB
    API --> FILES
    API -->|native secure read/write| KEYS
    API --> PDF
    API --> OLLAMA
  end
  subgraph NETWORK[Network]
    JOBS[Permitted public job APIs]
    OPENAI[Optional OpenAI]
    PORTALS[Manual employer portals]
  end
  API -.->|read requests, SSRF validation| JOBS
  API -.->|per-request approval, job and skills| OPENAI
  UI -.->|user opens and submits manually| PORTALS
```

The PDF child has resource limits, not network/filesystem isolation against arbitrary
native code execution. Windows Credential Manager stores encrypted credential material;
ASTRA never stores a plaintext key in its database or export. Loopback API access by
another same-user process is a documented residual risk. `/demo` is a fictional UI;
only `ASTRA_DEMO_ONLY=1` disables every private API route at the server boundary.
