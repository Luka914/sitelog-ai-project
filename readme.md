# SiteLog AI

**Turning forgotten paper safety checklists and dead PDFs into prioritized, verified repair tickets in 10 seconds.**

Built for **DurHack 2026 & The Accenture Challenge**.

<img width="1280" height="580" alt="image" src="https://github.com/user-attachments/assets/c83586f2-2352-433a-ad99-4a91e2fe180a" />


---

## The Problem

Right now, when a site engineer spots a leaking valve or a frayed cable during a daily safety check, they write it on a paper clipboard. Even when companies think they have "digitised" that process, all they really do is scan the sheet into an unsearchable PDF or get someone to type it into an Excel spreadsheet days later—where it sits forgotten until the machine breaks.

* **61%** of business document processes still involve paper, and **48%** of enterprises expect paper usage to grow despite existing scanning tools (AIIM Benchmark Study, 2025).
* Paper field logs suffer from illegible handwriting, lost forms, and slow manual re-entry (*Frontiers in Built Environment*, 2023), delaying corrective maintenance until minor warnings become safety hazards (*Buildings*, 2025).

## How SiteLog AI Redesigns the Workflow

Instead of forcing workers to use rigid digital forms or leaving scanned PDFs sitting in folders, SiteLog AI turns any phone photo or webcam capture of a physical checklist straight into a triaged work order:

1. **Template-Free Capture:** Upload a photo or snap a live webcam shot of any printed or handwritten inspection sheet—no fixed form layout required.
2. **Hybrid OCR + LLM Parsing:** `RapidOCR` extracts every line of text and its exact coordinates locally, while Groq's LLM (`Llama 3.3 70B`) interprets context, identifies `FAIL` items or warning notes, and enforces a strict **Pydantic** schema.
3. **Visual Proof Cropping:** `Pillow` crops the exact bounding box of the engineer's note from the original photo and attaches it directly to the ticket so supervisors can verify what was written in seconds.
4. **Cross-Inspection Memory (`SQLite`):** Before creating a ticket, the system checks past inspections for that exact machine ID. If a minor warning keeps recurring across weeks, Python automatically escalates it to **`CRITICAL`**.
5. **Deterministic Rules & Human-in-the-Loop:** Python assigns strict repair deadlines (SLAs), flags missing inspector signatures for compliance audits, routes low-confidence handwriting (`< 75%`) to manual verification, and requires supervisor approval (`Approve & Dispatch` $\rightarrow$ `Mark as Fixed`).

---

## Tech Stack

* **Backend:** Python, FastAPI, Uvicorn, Pydantic
* **OCR & Vision Cropping:** `rapidocr-onnxruntime`, `Pillow`, `NumPy`
* **LLM Reasoning:** Groq REST API (`llama-3.3-70b-versatile`) with structured JSON validation
* **Database:** SQLite (`sitelog.db` with WAL mode)
* **Frontend:** HTML, Tailwind CSS, Vanilla JavaScript (WebRTC webcam capture + live DB inspector)

---

## Quick Start

1. Clone & Navigate to the Project
```bash
git clone https://github.com/Luka914/sitelog-ai-project.git
cd sitelog ai project

### 2. Install Dependencies
python -m pip install -r requirements.txt

### 3. Add Your Groq API Key
Create a .env file in the sitelog ai project root folder:
GROQ_API_KEY=gsk_your_api_key_here

### 4. Run the Server
python -m uvicorn main:app --reload

Open http://127.0.0.1:8000 in your browser.


### Testing the Live Demo Scenario
The SQLite database automatically seeds two past oil warnings for GENERATOR-07 on startup. To test repeat-fault escalation:

Write a quick note on paper (or use a sample image) containing:

Asset ID: GENERATOR-07

Item: Oil Seal - FAIL - Oil leaking onto floor + loud knocking

Upload the photo or capture it via webcam on the Scanner & Tickets tab.

SiteLog AI detects the 2 prior warnings in inspection_history, auto-escalates the new ticket to CRITICAL (4-Hour Lockout SLA), and attaches the cropped image proof.

Switch to the Database Viewer (sitelog.db) tab at the top of the UI to inspect the live SQLite tables or click Reset Demo Data between pitches.
