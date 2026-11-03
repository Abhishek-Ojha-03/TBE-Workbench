"""
TBE Workbench API — FastAPI entry point.

This is the "new front door" discussed in frontend/ARCHITECTURE.md Section 6:
a REST layer the Next.js frontend can call over the network, since a
browser-based app has no direct access to Python/the database/API keys the
way the current Streamlit UI does. Every route here wraps EXISTING business
logic in db/, ai/, rules/, outputs/ — none of that logic is duplicated or
rewritten here.

Run with:  uvicorn api.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.connection import init_db
from api.routes import (
    tenders,
    specification,
    bidders,
    baseline,
    deliverables,
    working_excel,
    findings,
    reports,
    commercial,
    accuracy,
    archive,
)

app = FastAPI(
    title="TBE Workbench API",
    description="REST API wrapping the existing TBE Workbench Python backend.",
    version="0.1.0",
)

# Allow the local Next.js dev server to call this API. Tighten this list
# (and move to an env-driven config) before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3100",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    # Same init_db() the Streamlit app calls — creates tables + FTS setup
    # if they don't already exist. Safe to call repeatedly (idempotent).
    init_db()


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(tenders.router)
app.include_router(specification.router)
app.include_router(bidders.router)
app.include_router(baseline.router)
app.include_router(deliverables.router)
app.include_router(working_excel.router)
app.include_router(findings.tenders_router)
app.include_router(findings.findings_router)
app.include_router(reports.router)
app.include_router(commercial.router)
app.include_router(accuracy.router)
app.include_router(archive.router)
