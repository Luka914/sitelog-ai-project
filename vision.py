import json
import os
import urllib.error
import urllib.request
import uuid
from io import BytesIO
import numpy as np
from PIL import Image
from dotenv import load_dotenv, find_dotenv
from schemas import InspectionExtraction

# Searches both sitelog-ai/ and parent folders for .env, and cleans accidental spaces/quotes
load_dotenv(find_dotenv())
GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip().strip('"').strip("'")

# Folder where cropped handwriting proof images get saved
CROPS_DIR = os.path.join("static", "crops")
os.makedirs(CROPS_DIR, exist_ok=True)

# Load local OCR engine once when server starts
try:
    from rapidocr_onnxruntime import RapidOCR
    ocr_engine = RapidOCR()
except ImportError:
    ocr_engine = None


def get_groq_text_model() -> str:
    """Checks your Groq key and picks the best available text model."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing! Check your .env file and save it (Ctrl+S).")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/models",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "User-Agent": "SiteLogAI/1.0",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            all_ids = [m["id"] for m in data.get("data", []) if m.get("active", True)]
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Groq API Key error (HTTP {e.code}): {err}")

    print("Active models on your Groq key:", all_ids)

    # Prefer Llama 3.3 70B if available, otherwise pick the first active chat model
    for preferred in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"):
        if preferred in all_ids:
            return preferred

    skip = ("whisper", "guard", "tts", "playai", "embed", "orpheus")
    chat_models = [m for m in all_ids if not any(s in m.lower() for s in skip)]
    if not chat_models:
        raise RuntimeError(f"No usable chat models found on Groq key. Available: {all_ids}")
    return chat_models[0]


def run_local_ocr(image_bytes: bytes) -> list[dict]:
    """Reads every line of text and its exact 0-1000 bounding box from the photo locally."""
    if ocr_engine is None:
        raise RuntimeError("Run 'python -m pip install rapidocr-onnxruntime' in your terminal first.")

    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    width, height = img.size

    # Run RapidOCR on the image array
    result, _ = ocr_engine(np.array(img))
    if not result:
        return []

    lines = []
    for idx, (box, text, conf) in enumerate(result):
        # Convert 4 corner pixel points into [ymin, xmin, ymax, xmax] on a 0-1000 scale
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        box_2d = [
            int((min(ys) / height) * 1000),
            int((min(xs) / width) * 1000),
            int((max(ys) / height) * 1000),
            int((max(xs) / width) * 1000),
        ]
        lines.append({
            "line_id": idx,
            "text": text,
            "ocr_confidence": round(float(conf), 2),
            "box_2d": box_2d,
        })

    return lines


def analyze_checklist_image(image_bytes: bytes, mime_type: str) -> InspectionExtraction:
    """Step 1: Extracts text + boxes via local OCR. Step 2: Parses issues with Groq LLM."""
    ocr_lines = run_local_ocr(image_bytes)
    print("OCR extracted lines:", ocr_lines)

    if not ocr_lines:
        raise RuntimeError("OCR could not read any text in this image. Try a clearer, well-lit photo.")

    model_name = get_groq_text_model()

    prompt = f"""You are an industrial safety inspection parser.
Below are the OCR text lines and bounding boxes extracted from a photo of a paper safety checklist:

{json.dumps(ocr_lines, indent=2)}

Analyze these OCR lines and return ONLY valid JSON matching this exact structure:
{{
  "asset_id": "GENERATOR-07",
  "inspector_name": "Luka T.",
  "inspection_date": "2026-11-14",
  "signature_present": false,
  "issues": [
    {{
      "item_name": "Oil Seal",
      "status": "FAIL",
      "handwritten_note": "Oil leaking onto floor + loud knocking",
      "severity_hint": "CRITICAL",
      "confidence": 0.92,
      "box_2d": [410, 120, 520, 880]
    }}
  ]
}}

Rules:
- Include ONLY items marked FAIL, unchecked/broken, or containing warning notes.
- "status" must be strictly "FAIL" or "WARNING".
- "severity_hint" must be strictly "LOW", "MEDIUM", "HIGH", or "CRITICAL".
- Copy the exact "box_2d" and "ocr_confidence" (as "confidence") from the matching OCR line for each issue.
- If no items failed or had warnings, return "issues": []."""

    payload = {
        "model": model_name,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    }

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "SiteLogAI/1.0",
        },
        method="POST",
    )

    try:
        print(f"Sending OCR lines to Groq ({model_name})...")
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_json = data["choices"][0]["message"]["content"]
            return InspectionExtraction.model_validate_json(raw_json)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Groq error (HTTP {e.code}): {err_body}")


def crop_evidence(image_bytes: bytes, box_2d: list) -> str:
    """Crops the exact bounding box [ymin, xmin, ymax, xmax] out of the photo as proof."""
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    width, height = img.size

    if not box_2d or len(box_2d) != 4:
        cropped = img
    else:
        ymin, xmin, ymax, xmax = [float(v) for v in box_2d]
        left = max(0, int((xmin / 1000) * width) - 20)
        top = max(0, int((ymin / 1000) * height) - 20)
        right = min(width, int((xmax / 1000) * width) + 20)
        bottom = min(height, int((ymax / 1000) * height) + 20)

        if right <= left or bottom <= top:
            cropped = img
        else:
            cropped = img.crop((left, top, right, bottom))

    filename = f"{uuid.uuid4().hex[:10]}.jpg"
    filepath = os.path.join(CROPS_DIR, filename)
    cropped.save(filepath, format="JPEG", quality=90)

    return f"/static/crops/{filename}"