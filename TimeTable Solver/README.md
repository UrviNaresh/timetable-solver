---
title: Timetable Solver
emoji: 📅
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# College Timetable Solver (CP-SAT)

Exact timetable solver — OR-Tools CP-SAT. Har data par 0-gap solution
dhoondta hai, ya saaf bolega ki impossible hai.

Ye ek FastAPI server hai. College Timetable Generator app isse
`POST /solve` karke timetable banwati hai.

## Endpoints
- `GET  /` → `{"ok": true, "service": "timetable-solver"}`
- `POST /solve` → `{"status": "...", "placements": {...}}`

## POST /solve body
```json
{ "events": [...], "slots": [...], "days": [...],
  "resources": [...], "time_limit": 300 }
```

## Files
- `solver.py` — CP-SAT model (scheduling + rooms + saare rules)
- `server.py` — FastAPI wrapper
- `Dockerfile` — Hugging Face Spaces (Docker) ke liye
- `requirements.txt` — dependencies
