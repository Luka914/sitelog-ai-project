import traceback
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from db import init_db, get_conn, log_issue_to_history
from vision import analyze_checklist_image, crop_evidence
from rules import evaluate_ticket_rules

app = FastAPI(title="SiteLog AI")

init_db()
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_ui():
    """Serves the main webpage."""
    return FileResponse("static/index.html")


@app.post("/api/scan")
async def scan_checklist(file: UploadFile = File(...)):
    """Scans an uploaded checklist photo, creates tickets, and logs history."""
    try:
        image_bytes = await file.read()
        mime_type = file.content_type or "image/jpeg"

        # Step 1: Extract text with RapidOCR and parse issues with Groq
        extraction = analyze_checklist_image(image_bytes, mime_type)

        conn = get_conn()
        created_tickets = []

        for issue in extraction.issues:
            crop_url = crop_evidence(image_bytes, issue.box_2d)
            decision = evaluate_ticket_rules(
                asset_id=extraction.asset_id,
                signature_present=extraction.signature_present,
                issue=issue,
            )

            cur = conn.execute(
                """
                INSERT INTO tickets (
                    asset_id, item_name, handwritten_note, priority, sla_deadline,
                    escalation_reason, confidence, crop_url, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    extraction.asset_id.upper(),
                    issue.item_name,
                    issue.handwritten_note,
                    decision["priority"],
                    decision["sla_deadline"],
                    decision["escalation_reason"],
                    issue.confidence,
                    crop_url,
                    decision["status"],
                    datetime.now().strftime("%H:%M:%S"),
                ),
            )
            created_tickets.append(cur.lastrowid)

            # Log into inspection_history so future scans detect repeat faults
            log_issue_to_history(
                extraction.asset_id,
                issue.item_name,
                issue.handwritten_note,
                conn=conn,
            )
            conn.commit()

        conn.close()

        return {
            "asset_id": extraction.asset_id,
            "inspector": extraction.inspector_name,
            "signature_present": extraction.signature_present,
            "tickets_created": len(created_tickets),
        }

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(e).__name__}: {str(e)}"},
        )


@app.get("/api/tickets")
def list_tickets():
    """Returns all tickets for the main dashboard."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tickets ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/tickets/{ticket_id}/approve")
def approve_ticket(ticket_id: int):
    """Step 1 of workflow: Supervisor approves and dispatches the repair ticket."""
    conn = get_conn()
    cur = conn.execute(
        "UPDATE tickets SET status = 'DISPATCHED' WHERE id = ?",
        (ticket_id,),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ok": True}


@app.post("/api/tickets/{ticket_id}/fix")
def fix_ticket(ticket_id: int):
    """Step 2 of workflow: Engineer marks a dispatched ticket as FIXED."""
    conn = get_conn()
    cur = conn.execute(
        "UPDATE tickets SET status = 'FIXED' WHERE id = ?",
        (ticket_id,),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ok": True}


@app.get("/api/database")
def view_database():
    """Returns both SQLite tables so you can inspect the live database on the website."""
    conn = get_conn()
    tickets = [dict(r) for r in conn.execute("SELECT * FROM tickets ORDER BY id DESC").fetchall()]
    history = [dict(r) for r in conn.execute("SELECT * FROM inspection_history ORDER BY id DESC").fetchall()]
    conn.close()
    return {"tickets": tickets, "history": history}


@app.post("/api/reset-demo")
def reset_demo():
    """Resets the database back to the clean 2-warning GENERATOR-07 demo state."""
    conn = get_conn()
    conn.execute("DELETE FROM tickets")
    conn.execute("DELETE FROM inspection_history")
    seed_rows = [
        ("GENERATOR-07", "Oil Seal", "Minor oil misting near lower gasket", "2026-10-28"),
        ("GENERATOR-07", "Oil Seal", "Small oil drip spotted after 4hr run", "2026-11-05"),
    ]
    conn.executemany(
        "INSERT INTO inspection_history (asset_id, item_name, note, logged_date) VALUES (?, ?, ?, ?)",
        seed_rows,
    )
    conn.commit()
    conn.close()
    return {"ok": True}