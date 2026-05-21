from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import shutil
import os
from backend.ocr.extract_text import (
    extract_text_from_pdf,
    extract_text_from_image
)

from backend.chatbot.gemini_ai import (
    analyze_medical_report,
    medical_chatbot
)

from backend.schemas import ChatRequest


# =========================
# FastAPI App
# =========================

app = FastAPI(
    title="Medical AI Backend",
    description="AI Medical Report Analyzer + Chatbot",
    version="1.0.0"
)


# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Upload Folder Setup
# =========================

UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================
# Home Route
# =========================

@app.get("/")
def home():
    return {
        "message": "Medical AI Backend Running Successfully"
    }


# =========================
# Upload Report API
# =========================

@app.post("/upload-report")
async def upload_report(file: UploadFile = File(...)):

    try:

        # Save uploaded file
        file_path = os.path.join(
            UPLOAD_FOLDER,
            file.filename
        )

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # =========================
        # OCR Extraction
        # =========================

        extracted_text = ""

        if file.filename.endswith(".pdf"):
            extracted_text = extract_text_from_pdf(file_path)

        elif file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".avif")):
            extracted_text = extract_text_from_image(file_path)

        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file format. Please upload PDF, PNG, JPG, JPEG, or AVIF."
            )

        # =========================
        # AI Analysis
        # =========================

        ai_analysis = analyze_medical_report(extracted_text, file_path)
        # =========================
        # Response
        # =========================

        return {
            "success": True,
            "filename": file.filename,
            "extracted_text": extracted_text[:1500],
            "document_type": ai_analysis.get("document_type", "Lab Report"),
            "ai_analysis": ai_analysis
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================
# Upload X-Ray API
# =========================

@app.post("/analyze-xray")
async def analyze_xray(file: UploadFile = File(...)):

    try:

        # Save uploaded file
        file_path = os.path.join(
            UPLOAD_FOLDER,
            file.filename
        )

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Vision Analysis
        from backend.chatbot.gemini_ai import analyze_xray_image
        xray_analysis = analyze_xray_image(file_path)

        return {
            "success": True,
            "filename": file.filename,
            "scan_findings": xray_analysis.get("scan_findings", ""),
            "potential_concerns": xray_analysis.get("potential_concerns", ""),
            "suggested_steps": xray_analysis.get("suggested_steps", ""),
            "doctor_recommendation": xray_analysis.get("doctor_recommendation", ""),
            "detections": xray_analysis.get("detections", ["No anomalies detected"]),
            "confidence": xray_analysis.get("confidence", "N/A"),
            "summary": xray_analysis.get("summary", ""),
            "diet": xray_analysis.get("diet", ""),
            "exercise": xray_analysis.get("exercise", ""),
            "medicines": xray_analysis.get("medicines", ""),
            "lifestyle": xray_analysis.get("lifestyle", ""),
            "recommendation": xray_analysis.get("recommendation", "")
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# =========================
# Medical Chatbot API
# =========================

@app.post("/chat")
async def chat_with_ai(data: ChatRequest):

    try:

        answer = medical_chatbot(
            data.question,
            data.report_text
        )
        return {
            "success": True,
            "question": data.question,
            "answer": answer
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


