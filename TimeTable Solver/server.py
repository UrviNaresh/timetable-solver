"""FastAPI server for the College Timetable CP-SAT solver.

Endpoints:
  GET  /                 -> {"ok": true}
  POST /solve            -> {"status": ..., "placements": {...}}   (sync — chhote data)
  POST /solve_async      -> {"job_id": "...", "status": "running"} (bada data — polling)
  GET  /result/{job_id}  -> {"status": "running"|"done"|"error", ...}

Kyun async: bada data solve hone me kai minute lagte hain — lambi HTTP
request beech me toot jati hai ("Backend error"). Async me app job submit
karti hai aur chhoti-chhoti request se result poll karti hai — isliye koi
drop nahi hota.
"""
import os
import threading
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from solver import solve

app = FastAPI(title="College Timetable Solver")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: Dict[str, Dict[str, Any]] = {}


class SolveReq(BaseModel):
    events: List[Dict[str, Any]]
    slots: List[Dict[str, Any]]
    days: List[str]
    resources: List[Dict[str, Any]]
    time_limit: Optional[int] = 300


def _workers():
    # chhote instance (Render free = 0.1 CPU / 512MB) par 8 workers RAM khatam
    # karte hain — isliye CPU ke hisaab se
    n = os.cpu_count() or 1
    return max(1, min(4, n))


def _payload(req: SolveReq):
    return {
        "events": req.events,
        "slots": req.slots,
        "days": req.days,
        "resources": req.resources,
    }


@app.get("/")
def root():
    return {"ok": True, "service": "timetable-solver"}


@app.get("/health")
def health():
    return {"ok": True, "jobs": len(JOBS)}


@app.post("/solve")
def solve_endpoint(req: SolveReq):
    out = solve(_payload(req), time_limit=int(req.time_limit or 300), workers=_workers())
    out["workers"] = _workers()
    return out


def _run_job(job_id: str, data: dict, time_limit: int, workers: int):
    try:
        out = solve(data, time_limit=time_limit, workers=workers)
        JOBS[job_id] = {"status": "done", "result": out}
    except Exception as e:  # noqa: BLE001
        JOBS[job_id] = {"status": "error", "error": str(e)}


@app.post("/solve_async")
def solve_async(req: SolveReq):
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "running"}
    # purane jobs saaf karo (memory na bhare)
    if len(JOBS) > 30:
        for k in list(JOBS.keys())[: len(JOBS) - 30]:
            if JOBS[k].get("status") != "running":
                JOBS.pop(k, None)
    t = threading.Thread(
        target=_run_job,
        args=(job_id, _payload(req), int(req.time_limit or 300), _workers()),
        daemon=True,
    )
    t.start()
    return {"job_id": job_id, "status": "running"}


@app.get("/result/{job_id}")
def result(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        return {"status": "unknown"}
    if j.get("status") == "running":
        return {"status": "running"}
    if j.get("status") == "error":
        return {"status": "error", "error": j.get("error")}
    return {"status": "done", "result": j.get("result")}
