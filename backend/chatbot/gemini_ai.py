import os
import requests
import json
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Global state for chatbot conversation context memory
last_report_text = ""
conversation_history = []
conversation_language = None

def detect_user_language(text: str) -> str:
    """
    Detects the language of the input text.
    Returns one of: 'gujarati', 'hindi_hinglish', 'english', or 'unknown'.
    """
    if not text:
        return 'english'
        
    text_lower = text.lower()
    
    # 1. Explicit request words
    if any(kw in text_lower for kw in ["gujarati", "gujrati", "guj", "ગુજરાતી"]):
        return "gujarati"
    if any(kw in text_lower for kw in ["hindi", "hinglish", "हिन्दी"]):
        return "hindi_hinglish"
    if any(kw in text_lower for kw in ["english", "angreji", "angrezi"]):
        return "english"
        
    # 2. Check for script characters
    # Gujarati character range: \u0a80-\u0aff
    if any('\u0a80' <= char <= '\u0aff' for char in text):
        return "gujarati"
    # Devanagari character range: \u0900-\u097f
    if any('\u0900' <= char <= '\u097f' for char in text):
        return "hindi_hinglish"
        
    # 3. Check for Hinglish and Gujarati-in-Latin words/phrases
    hinglish_markers = {
        "samjhao", "samjhaye", "samjho", "batao", "bataiye", "meri", "mera", "mere", "kya", "hai", 
        "nahi", "nhi", "kuch", "aapke", "samjhayein", "diye", "liye", "gaya", "raha", "rahi", "hoga", "sakte"
    }
    gujarati_markers = {
        "samjhavo", "samjhavi", "lakhajo", "lakho", "shu", "che", "chhe", "maru", "mari", "mara", "pan", 
        "nathi", "ane", "takarif", "dukhavo", "dava"
    }
    
    words = re.findall(r'[a-zA-Z]+', text_lower)
    
    gu_count = sum(1 for w in words if w in gujarati_markers)
    hi_count = sum(1 for w in words if w in hinglish_markers)
    
    if gu_count > 0 and gu_count >= hi_count:
        return "gujarati"
    if hi_count > 0 and hi_count > gu_count:
        return "hindi_hinglish"
        
    # 4. Fallback: use langdetect library for a probabilistic check
    try:
        from langdetect import detect
        lang = detect(text)
        if lang == 'gu':
            return 'gujarati'
        elif lang in ['hi', 'ne', 'mr']: # Hindi, Nepali, Marathi
            return 'hindi_hinglish'
        elif lang == 'en':
            # Confirm it's English only if no Hinglish or Gujarati markers are present
            if not any(w in hinglish_markers for w in words) and not any(w in gujarati_markers for w in words):
                return 'english'
    except Exception:
        pass
        
    return 'unknown'


def parse_json_safely(text: str) -> dict:
    """
    Safely extracts and parses JSON from text, even if wrapped in markdown or surrounding text.
    """
    if not text:
        return None
    cleaned = text.strip()
    
    # Try finding the first '{' and last '}'
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        cleaned = cleaned[first_brace:last_brace+1]
        
    try:
        return json.loads(cleaned)
    except Exception:
        pass
        
    # Attempt to clean trailing commas before closing braces/brackets
    import re
    cleaned_sub = re.sub(r',\s*([\]}])', r'\1', cleaned)
    try:
        return json.loads(cleaned_sub)
    except Exception:
        pass
        
    return None

def clean_raw_text_fallback(text) -> str:
    """
    Cleans raw text (that might look like broken JSON, lists, or dicts) into a reader-friendly clinical paragraph/bullets,
    ensuring no raw JSON-style brackets or raw keys appear in the UI.
    """
    if not text:
        return "Clinical findings summary is available upon request."
    
    # Handle list input recursively
    if isinstance(text, list):
        items = []
        for item in text:
            cleaned_item = clean_raw_text_fallback(item)
            if cleaned_item:
                for line in cleaned_item.splitlines():
                    val = line.strip().strip('*').strip('-').strip('•').strip()
                    if val:
                        items.append(val)
        return "\n".join(f"* {i}" for i in items) if items else "Clinical findings summary is available upon request."

    # Handle dictionary input recursively
    if isinstance(text, dict):
        items = []
        for k, v in text.items():
            cleaned_val = clean_raw_text_fallback(v)
            if cleaned_val:
                for line in cleaned_val.splitlines():
                    val = line.strip().strip('*').strip('-').strip('•').strip()
                    if val:
                        items.append(val)
        return "\n".join(f"* {i}" for i in items) if items else "Clinical findings summary is available upon request."

    # Convert to string and clean
    cleaned = str(text).strip()
    
    # Try parsing stringified JSON list/array if it looks like one
    if cleaned.startswith("[") and cleaned.endswith("]"):
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return clean_raw_text_fallback(parsed)
        except Exception:
            pass

    # Try parsing stringified JSON object if it looks like one
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return clean_raw_text_fallback(parsed)
        except Exception:
            pass
            
    # Handle line-by-line fallback cleaning if JSON braces/brackets leak as strings
    if "{" in cleaned or "}" in cleaned or "[" in cleaned or "]" in cleaned:
        lines = []
        for line in cleaned.splitlines():
            line = line.strip()
            if not line or line in ["{", "}", "[", "]", "],", "},"]:
                continue
            # Strip common key names
            for key in ["scan_findings", "potential_concerns", "suggested_steps", "doctor_recommendation", 
                        "summary", "diseases", "diet", "exercise", "medicines", "lifestyle", "observations", "next_steps"]:
                if f'"{key}":' in line or f'"{key}" :' in line:
                    line = line.split(":", 1)[1].strip()
            # Clean outer quotes and trailing commas
            line = line.strip(',').strip('"').strip("'").strip()
            if line:
                lines.append(line)
        if lines:
            return "\n".join(f"* {l}" if not l.startswith(("*", "-", "•")) else l for l in lines)
            
    return cleaned


def classify_document(file_path: str = None, extracted_text: str = None) -> str:
    """
    Classifies a medical document into one of 4 categories:
    - "Lab Report"
    - "Prescription"
    - "X-ray / Scan"
    - "General Medical Document"
    
    If file_path is an image, we use multimodal Gemini by sending both the image and the OCR text.
    If file_path is a PDF, we send the extracted text.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing from environment or .env file.")
    
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    # Base classification prompt
    prompt = """
    You are a professional Medical Document Classifier AI.
    Analyze the provided document (text contents and/or visual layout) and classify it into exactly one of these four categories:
    
    1. "Lab Report"
       Choose this for blood test reports, pathology reports, metabolic panels, thyroid reports, urine tests, lipid panels, diagnostic lab sheets, and printed laboratory tabular data.
       
    2. "Prescription"
       Choose this for doctor's prescriptions. This includes handwritten or printed scripts containing lists of medicine names, dosages, frequencies, symbols like "Rx", doctor's signatures/notes, or instructions on when to take medications (e.g., "1-0-1", "before food").
       
    3. "X-ray / Scan"
       Choose this for radiological or diagnostic imaging scans, including chest X-rays, MRI scans, CT scans, ultrasounds, echocardiograms, mammograms, or any image displaying bone, organ, or soft tissue structures.
       
    4. "General Medical Document"
       Choose this for any other medical document, such as hospital discharge summaries, medical certificates, insurance claims, medical bills, referral letters, doctor contact sheets, or educational medical pamphlets.

    Your response must be a valid JSON object containing exactly one key: "document_type".
    The value must be exactly one of: "Lab Report", "Prescription", "X-ray / Scan", "General Medical Document".
    
    Do not wrap the response in markdown code blocks. Respond only with the raw JSON object.
    """
    
    parts = []
    is_image = False
    
    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        is_image = ext in [".png", ".jpg", ".jpeg", ".avif"]
        
        if is_image:
            import base64
            try:
                with open(file_path, "rb") as image_file:
                    image_data = base64.b64encode(image_file.read()).decode("utf-8")
                
                if ext == ".png":
                    mime_type = "image/png"
                elif ext == ".avif":
                    mime_type = "image/avif"
                else:
                    mime_type = "image/jpeg"
                parts.append({
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": image_data
                    }
                })
            except Exception as e:
                print(f"Error reading image for classification: {e}")
                
    # Include text parts (if available)
    text_content = f"Classification prompt:\n{prompt}\n\n"
    if extracted_text:
        text_content += f"Extracted Document OCR Text:\n---\n{extracted_text}\n---\n"
    else:
        text_content += "No OCR text extracted from the document."
        
    parts.insert(0, {"text": text_content})
    
    payload = {
        "contents": [
            {
                "parts": parts
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            res_json = response.json()
            text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            
            # Strip markdown wrappers if present
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
                
            parsed = parse_json_safely(text)
            if parsed:
                doc_type = parsed.get("document_type")
                if doc_type in ["Lab Report", "Prescription", "X-ray / Scan", "General Medical Document"]:
                    return doc_type
    except Exception as e:
        print(f"Error in document classification: {e}")
        
    # Fallback heuristics if API call fails or yields invalid output
    text_lower = (extracted_text or "").lower()
    if any(k in text_lower for k in ["rx", "capsule", "tablet", "tab.", "cap.", "mg", "twice daily", "once daily", "prescription"]):
        return "Prescription"
    if any(k in text_lower for k in ["haemoglobin", "cholesterol", "wbc", "rbc", "platelet", "glucose", "serum", "lipid", "report"]):
        return "Lab Report"
    if any(k in text_lower for k in ["xray", "x-ray", "mri", "ct scan", "ultrasound", "chest view", "clinical history"]):
        return "X-ray / Scan"
        
    return "Lab Report"  # default fallback


def analyze_prescription(file_path: str = None, extracted_text: str = None) -> dict:
    """
    Analyzes a prescription image/PDF, extracting medicine names, dosage, timing, frequency, precautions, etc.
    Strictly avoids generating any exercise, cholesterol, diet, or lifestyle recommendations.
    Returns a dictionary matching the required response format.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing from environment or .env file.")
    
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    prompt = """
    You are an expert clinical pharmacist and AI prescription analyzer.
    Analyze this prescription document (OCR text and/or image).
    
    CRITICAL TONE & VERBOSITY SAFETY INSTRUCTIONS:
    - Never present any finding or diagnosis as absolute, sure, or confirmed. Frame all findings as potential, possible, or observed features needing clinical correlation.
    - DO NOT use alarmist, aggressive, or panic-inducing wording. You must strictly avoid the following blacklisted terms:
      * "emergency" -> instead use "clinical evaluation recommended"
      * "high risk" / "critical" / "severe" -> instead use "specialist consultation advised"
      * "do not delay" / "immediate" / "at once" / "urgently" -> instead use "further assessment may be beneficial" or "prompt follow-up is recommended"
      * "diagnosed" / "diagnose" / "diagnosing" -> instead use "identified feature", "observed pattern", or "potential indication"
    - Friendly Clinical Tone: Write with a warm, caring, reassuring clinical doctor tone.
    - Detailed Presentation: Mix a descriptive introductory paragraph (1-2 sentences) explaining the status/findings with 2 to 4 detailed but readable bullet points.
    - Medical Emojis & Inline SVGs: Integrate appropriate medical emojis naturally. Also, embed a small, lightweight inline SVG medical icon near the beginning of each markdown field.
      * For Medicines/Usage, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="9" width="20" height="6" rx="3" transform="rotate(-45 12 12)"/><line x1="7.5" y1="16.5" x2="16.5" y2="7.5"/></svg>
      * For Notes, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>

    DYNAMIC EXTRACTION RULES:
    - Focus strictly and exclusively on the actual document contents. Do NOT hallucinate or assume generic medical conditions unless explicitly noted in the prescription.
    - If a specific field or detail is not present in the document, you MUST return exactly one single, natural fallback bullet point confirming this (e.g., "* No safety precautions are explicitly noted in this script."). Do NOT include generic boilerplate advice or multiple bullet points in this case.

    Your instructions:
    1. Focus ONLY on extracting the medicines, their dosage, timing, frequency, precautions, and possible purposes.
    2. DO NOT generate any general exercise protocols, pathology summaries, cholesterol advice, or lifestyle suggestions.
    3. Return a JSON object with exactly these four keys:
       - "medicines_detected": A list of medicines found (include name, strength, and possible purpose. Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated. Prefix/decorate with the Pill inline SVG).
       - "suggested_usage": Guidelines on dosage, timing, and frequency (Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated. Prefix/decorate with the Pill inline SVG).
       - "notes": Any safety precautions, warning notes, or critical remarks (Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated. Prefix/decorate with the Shield Alert inline SVG).
       - "disclaimer": Always return exactly "Consult your doctor before taking medication."
    
    Formatting rules for the JSON values:
    - For "medicines_detected", "suggested_usage", and "notes", start each list item with a bullet point character like "* ".
    - If the category has findings/recommendations, provide exactly 2 to 4 short markdown bullet points (max 12 words per bullet point).
    - If the category is not relevant or has no findings, provide exactly 1 single markdown bullet point (max 12 words) stating this.
    - Keep bullet points short, clear, and professional.
    - Respond ONLY with the JSON object. Do not wrap it in markdown code blocks.
    """
    
    parts = [{"text": f"{prompt}\n\nPrescription OCR Text:\n---\n{extracted_text}\n---"}]
    
    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".png", ".jpg", ".jpeg", ".avif"]:
            import base64
            try:
                with open(file_path, "rb") as image_file:
                    image_data = base64.b64encode(image_file.read()).decode("utf-8")
                if ext == ".png":
                    mime_type = "image/png"
                elif ext == ".avif":
                    mime_type = "image/avif"
                else:
                    mime_type = "image/jpeg"
                parts.append({
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": image_data
                    }
                })
            except Exception as e:
                print(f"Error reading prescription image: {e}")
            
    payload = {
        "contents": [
            {
                "parts": parts
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            res_json = response.json()
            text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            
            # Strip markdown wrappers if present
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
                
            parsed = parse_json_safely(text)
            if parsed:
                # Validate keys
                for key in ["medicines_detected", "suggested_usage", "notes", "disclaimer"]:
                    if key not in parsed:
                        parsed[key] = "* No information extracted."
                    else:
                        # Clean raw JSON format from inside values just in case
                        parsed[key] = clean_raw_text_fallback(parsed[key])
                if not parsed.get("disclaimer") or parsed["disclaimer"] == "* No information extracted.":
                    parsed["disclaimer"] = "Consult your doctor before taking medication."
                return parsed
    except Exception as e:
        print(f"Error in prescription analysis: {e}")
        
    return {
        "medicines_detected": "* Could not parse medicines separately.",
        "suggested_usage": "* Could not parse instructions separately.",
        "notes": "* Please read the raw prescription scan carefully.",
        "disclaimer": "Consult your doctor before taking medication."
    }


def analyze_general_document(file_path: str = None, extracted_text: str = None) -> dict:
    """
    Analyzes a general medical document (discharge summary, bill, cert, etc.)
    and returns a summary, clinical details, next steps, and disclaimer.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing from environment or .env file.")
    
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    prompt = """
    You are an expert Clinical Administrator and AI Medical assistant.
    Analyze this general medical document (OCR text).
    
    CRITICAL TONE & VERBOSITY SAFETY INSTRUCTIONS:
    - Never present any finding or diagnosis as absolute, sure, or confirmed. Frame all findings as potential, possible, or observed features needing clinical correlation.
    - DO NOT use alarmist, aggressive, or panic-inducing wording. You must strictly avoid the following blacklisted terms:
      * "emergency" -> instead use "clinical evaluation recommended"
      * "high risk" / "critical" / "severe" -> instead use "specialist consultation advised"
      * "do not delay" / "immediate" / "at once" / "urgently" -> instead use "further assessment may be beneficial" or "prompt follow-up is recommended"
      * "diagnosed" / "diagnose" / "diagnosing" -> instead use "identified feature", "observed pattern", or "potential indication"
    - Friendly Clinical Tone: Write with a warm, caring, reassuring clinical doctor tone.
    - Detailed Presentation: Mix a descriptive introductory paragraph (1-2 sentences) explaining the status/findings with 2 to 4 detailed but readable bullet points.
    - Medical Emojis & Inline SVGs: Integrate appropriate medical emojis naturally. Also, embed a small, lightweight inline SVG medical icon near the beginning of each markdown field.
      * For Summary, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>
      * For Observations, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      * For Next Steps, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>

    DYNAMIC EXTRACTION RULES:
    - Focus strictly and exclusively on the actual document contents. Do NOT hallucinate or assume generic medical conditions unless explicitly noted in the document.
    - If a specific field or detail is not present in the document, you MUST return exactly one single, natural fallback bullet point confirming this (e.g., "* No general administrative observations are indicated in this document."). Do NOT include generic boilerplate advice or multiple bullet points in this case.

    Your instructions:
    1. Extract a clinical summary, key details/observations, and recommendations/next steps.
    2. Return a JSON object with exactly these four keys:
       - "summary": A clinical summary of the document (formatted as short paragraphs, decorated with the Wellbeing Sun inline SVG).
       - "observations": Key observations, figures, or administrative details found (Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated. Decorated with the Shield Alert inline SVG).
       - "next_steps": Recommended action items, follow-ups, or next steps (Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated. Decorated with the Heart Rate / Activity inline SVG).
       - "disclaimer": Always return exactly "Consult your doctor or hospital administrator for confirmation."
          
      Formatting rules for the JSON values:
      - For "observations" and "next_steps", start each list item with a bullet point character like "* ".
      - If the category has findings/recommendations, provide exactly 2 to 4 short markdown bullet points (max 12 words per bullet point).
      - If the category is not relevant or has no findings, provide exactly 1 single markdown bullet point (max 12 words) stating this.
      - Keep bullet points short, clear, and professional.
      - Respond ONLY with the JSON object. Do not wrap in markdown code blocks.
    """
    
    parts = [{"text": f"{prompt}\n\nDocument OCR Text:\n---\n{extracted_text}\n---"}]
    
    payload = {
        "contents": [
            {
                "parts": parts
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            res_json = response.json()
            text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            
            # Strip markdown wrappers if present
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
                
            parsed = parse_json_safely(text)
            if parsed:
                for key in ["summary", "observations", "next_steps", "disclaimer"]:
                    if key not in parsed:
                        parsed[key] = "No information provided."
                    else:
                        # Clean raw JSON format from inside values
                        parsed[key] = clean_raw_text_fallback(parsed[key])
                return parsed
    except Exception as e:
        print(f"Error in general document analysis: {e}")
        
    return {
        "summary": "Could not parse document summary.",
        "observations": "* Could not parse observations.",
        "next_steps": "* Check raw document stream for details.",
        "disclaimer": "Consult your doctor or hospital administrator for confirmation."
    }


def analyze_medical_report(report_text, file_path=None):
    """
    Analyzes a medical report text using the Gemini REST API.
    Detects the document type first, then runs the specialized workflow.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing from environment or .env file.")
    
    # 1. Detect Document Type
    doc_type = classify_document(file_path, report_text)
    
    # 2. Route based on Document Type
    if doc_type == "Prescription":
        result = analyze_prescription(file_path, report_text)
        result["document_type"] = "Prescription"
        return result
        
    elif doc_type == "General Medical Document":
        result = analyze_general_document(file_path, report_text)
        result["document_type"] = "General Medical Document"
        return result
        
    elif doc_type == "X-ray / Scan" and file_path:
        # If user uploaded an X-ray to standard route, run X-ray flow
        result = analyze_xray_image(file_path)
        result["document_type"] = "X-ray / Scan"
        return result
        
    # Default/Lab Report Flow
    model_name = os.getenv("GEMINI_MODEL", "gemini-pro")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    prompt = f"""
    You are an expert Clinical Document Analyzer. Analyze this extracted medical report text:

    {report_text}

    CRITICAL TONE & VERBOSITY SAFETY INSTRUCTIONS:
    - Never present any finding or diagnosis as absolute, sure, or confirmed. Frame all findings as potential, possible, or observed features needing clinical correlation.
    - DO NOT use alarmist, aggressive, or panic-inducing wording. You must strictly avoid the following blacklisted terms:
      * "emergency" -> instead use "clinical evaluation recommended"
      * "high risk" / "critical" / "severe" -> instead use "specialist consultation advised"
      * "do not delay" / "immediate" / "at once" / "urgently" -> instead use "further assessment may be beneficial" or "prompt follow-up is recommended"
      * "diagnosed" / "diagnose" / "diagnosing" -> instead use "identified feature", "observed pattern", or "potential indication"
    - Friendly Clinical Tone: Write with a warm, caring, reassuring clinical doctor tone.
    - Detailed Presentation: Mix a descriptive introductory paragraph (1-2 sentences) explaining the status/findings with 2 to 4 detailed but readable bullet points.
    - Medical Emojis & Inline SVGs: Integrate appropriate medical emojis naturally. Also, embed a small, lightweight inline SVG medical icon near the beginning of each markdown field.
      * For Summary, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>
      * For Pathology/Findings (diseases), use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      * For Diet, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/><path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/></svg>
      * For Exercise, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
      * For Medicines, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="9" width="20" height="6" rx="3" transform="rotate(-45 12 12)"/><line x1="7.5" y1="16.5" x2="16.5" y2="7.5"/></svg>
      * For Lifestyle, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4.82 4.82A9 9 0 0 0 12 19.08V22h3v-2.92A9 9 0 0 0 20.3 7.7"/><circle cx="12" cy="11" r="3"/></svg>

    DYNAMIC REALISTIC ANALYSIS RULES:
    - Avoid generic medical templates, placeholders, or copy-pasted advice. Do NOT default to suggesting anemia, blood sugar issues, or high cholesterol unless these are explicitly supported by abnormal values or specific findings in the report text.
    - Customize every card's response to the actual report data. If a category is not relevant or has no findings, provide exactly 1 single bullet point (max 12 words) stating this (e.g. "* General physical activity guidelines remain unaffected.").

    You must return a valid JSON object containing the analysis. The JSON must contain exactly these six keys:
    1. "summary": A concise clinical summary paragraph (2-3 sentences, cautious wording, decorated with the Wellbeing Sun inline SVG).
    2. "diseases": Key findings, abnormal parameters, or potential pathologies identified (Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; decorated with the Shield Alert inline SVG).
    3. "diet": Dietary advice or restrictions based on findings (Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated; decorated with the Diet inline SVG).
    4. "exercise": Physical activity protocols, warnings, or fitness recommendations (Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated; decorated with the Heart Rate / Activity inline SVG).
    5. "medicines": Recommended over-the-counter medicines, vitamins, supplements, or medical compounds (Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated; decorated with the Pill inline SVG).
    6. "lifestyle": Lifestyle suggestions, routines, stress, or sleep tips (Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated; decorated with the Stethoscope inline SVG).

    Formatting rules for the JSON values:
    - For keys 2-6, start each list item with a bullet point character like "* ".
    - If the category is indicated/relevant, provide exactly 2 to 4 bullet points. If the category is not indicated/relevant, provide exactly 1 single bullet point stating this (e.g., "* No pharmacological interventions are indicated by these laboratory findings.").
    - Keep bullet points short, clear, and professional (max 12 words per bullet point).
    - Respond ONLY with the JSON object. Do not wrap the JSON in markdown code blocks like ```json ... ```.
    """
    
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
    except Exception as e:
        raise RuntimeError(f"Connection to Gemini REST API failed: {str(e)}")
    
    if response.status_code != 200:
        raise ValueError(f"Invalid response from Gemini API (status code {response.status_code}): {response.text}")
        
    try:
        response_json = response.json()
    except Exception as e:
        raise ValueError(f"Invalid response from Gemini API (failed to parse JSON): {str(e)}")
    
    candidates = response_json.get("candidates")
    if not candidates or len(candidates) == 0:
        raise ValueError(f"No candidates returned from Gemini API. Full response: {response_json}")
        
    candidate = candidates[0]
    content = candidate.get("content")
    if not content:
        raise ValueError("Invalid response structure: 'content' field missing in candidate.")
        
    parts = content.get("parts")
    if not parts or len(parts) == 0:
        raise ValueError("Invalid response structure: 'parts' field missing or empty in candidate content.")
        
    text = parts[0].get("text")
    if not text:
        raise ValueError("Invalid response structure: 'text' field missing in candidate content parts.")
    
    text = text.strip()
    
    # Strip markdown wrapper if present
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        
    parsed_data = parse_json_safely(text)
    if parsed_data:
        required_keys = ["summary", "diseases", "diet", "exercise", "medicines", "lifestyle"]
        for key in required_keys:
            if key not in parsed_data:
                parsed_data[key] = "No information provided."
            else:
                # Clean raw JSON format from inside values
                parsed_data[key] = clean_raw_text_fallback(parsed_data[key])
        parsed_data["document_type"] = "Lab Report"
        return parsed_data
    else:
        # Fallback if AI output is not valid JSON
        cleaned_text = clean_raw_text_fallback(text)
        return {
            "document_type": "Lab Report",
            "summary": cleaned_text,
            "diseases": "Could not extract pathologies separately. Specialist consultation advised.",
            "diet": "Could not extract dietary advice separately. Clinical evaluation recommended.",
            "exercise": "Could not extract exercise protocol separately. Specialist consultation advised.",
            "medicines": "Could not extract recommended medicines separately. Clinical evaluation recommended.",
            "lifestyle": "Could not extract lifestyle suggestions separately. Further assessment may be beneficial."
        }



def medical_chatbot(question, report_text):
    """
    Answers a medical question based on the medical report and previous context using the Gemini REST API.
    """
    global last_report_text, conversation_history, conversation_language

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing from environment or .env file.")

    # Reset conversation history if the patient uploads a new report
    if report_text != last_report_text:
        conversation_history = []
        last_report_text = report_text
        conversation_language = None
        
    model_name = os.getenv("GEMINI_MODEL", "gemini-pro")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    # Format conversation history
    history_str = ""
    for msg in conversation_history[-10:]:
        history_str += f"{msg['role']}: {msg['content']}\n"

    # Automatic language detection & conversational memory
    clean_question = question
    if clean_question.startswith("[Hinglish Mode]"):
        clean_question = clean_question[len("[Hinglish Mode]"):].strip()
        detected_lang = 'hindi_hinglish'
    else:
        detected_lang = detect_user_language(clean_question)

    if detected_lang in ['gujarati', 'hindi_hinglish']:
        conversation_language = detected_lang
    elif detected_lang == 'english':
        if not conversation_language or any(kw in clean_question.lower() for kw in ["english", "in english", "angreji", "angrezi", "translate to english"]):
            conversation_language = 'english'
    
    if not conversation_language:
        conversation_language = 'english'

    # Build prompt instructions based on the active language memory
    if conversation_language == 'gujarati':
        lang_instruction = """
        Active Language is GUJARATI.
        - You MUST respond fully in Gujarati (using Gujarati script).
        - If the user asks in English but their active conversation context is Gujarati, respond in Gujarati.
        - Do not mix English or Hindi. Keep the Gujarati natural, simple, and clean.
        - Do not say you are more comfortable in English or mention any language limitations.
        - Translate all headings and bullet points to Gujarati.
          * E.g. "🩸 બ્લડ રિપોર્ટ અપડેટ", "🥗 શું મદદ કરી શકે:", "🏃 આરોગ્ય ટિપ્સ:", "💊 દવા:", "🩺 અસ્વીકરણ:"
        - Medical disclaimer in Gujarati: "🩺 કૃપા કરીને ક્લિનિકલ પુષ્ટિ માટે આ તારણોની ડૉક્ટર સાથે સમીક્ષા કરો." (Only append if query is medical/clinical in nature).
        """
    elif conversation_language == 'hindi_hinglish':
        lang_instruction = """
        Active Language is HINDI / HINGLISH.
        - You MUST respond in Hindi/Hinglish (mix of Hindi and English words as spoken naturally, or Hindi Devanagari script depending on user's input style).
        - If the user uses Hinglish/Hindi, reply naturally in Hindi/Hinglish. Do not default to English.
        - Do not say you are more comfortable in English or mention any language limitations.
        - Keep headings and formatting professional, utilizing natural Hindi/Hinglish.
          * E.g. "🩸 Blood Report Update", "🥗 Kya madad kar sakta hai:", "🏃 Health Tips:", "💊 Dawa:", "🩺 Disclaimer:"
        - Medical disclaimer in Hinglish/Hindi: "🩺 Doctor se clinical confirmation ke liye consult karein." (Only append if query is medical/clinical in nature).
        """
    else:
        lang_instruction = """
        Active Language is ENGLISH.
        - Respond in simple, clear, and professional English.
        - Medical disclaimer in English: "🩺 Please review these findings with a doctor for clinical confirmation." (Only append if query is medical/clinical in nature).
        """

    prompt = f"""
    You are MediVision AI, a supportive, highly conversational, and friendly AI doctor assistant, behaving like Gemini or a ChatGPT medical assistant. You help the patient understand their health data, medical report parameters, or imaging scans in a warm, empathetic, and human tone.

    MULTILINGUAL SYSTEM PROMPT RULES (CRITICAL):
    Always respond in the same language used by the user.
    Maintain the same conversational tone and language across the session.
    If the user uses Gujarati, reply fully in Gujarati.
    If the user uses Hindi or Hinglish, reply naturally in Hindi/Hinglish.
    Do not default to English.
    
    {lang_instruction}

    CRITICAL SAFETY & TONE INSTRUCTIONS:
    - Never present any finding or diagnosis as absolute, sure, or confirmed. Frame all findings as potential, possible, or observed features needing clinical correlation.
    - Strictly avoid alarmist, aggressive, or panic-inducing wording. You must strictly avoid the following blacklisted terms:
      * "emergency" -> instead use "clinical evaluation recommended"
      * "high risk" / "critical" / "severe" -> instead use "specialist consultation advised"
      * "do not delay" / "immediate" / "at once" / "urgently" -> instead use "further assessment may be beneficial" or "prompt follow-up is recommended"
      * "diagnosed" / "diagnose" / "diagnosing" -> instead use "identified feature", "observed pattern", or "potential indication"
    - Instead, use cautious clinical phrasing: "clinical evaluation recommended", "specialist consultation advised", "further assessment may be beneficial". Never make definitive diagnostic claims.

    CHATBOT RESPONSE STYLE RULES:
    1. Human & Supportive Tone: Be warm, friendly, reassuring, and conversational. Speak like a caring doctor, not a cold textbook.
    2. Simple Language: Use very simple language, short sentences, and avoid hard medical jargon. If you must use a medical term, explain it immediately in simple brackets in the active language.
    3. Medium Length: Keep responses medium length (not too long, not too short).
    4. Structural Formatting:
       - Use headings naturally.
       - Use bullet points for lists.
       - Keep paragraphs short (1-2 sentences).
    5. Emojis & Inline SVGs: Use relevant emojis naturally. In your responses, when explaining medical systems or recommendations, feel free to embed small, lightweight inline SVGs inside your text to visualize clinical components.
       * Blood drop: <svg class="medical-chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22a7 7 0 0 0 7-7c0-4.3-7-13-7-13S5 10.7 5 15a7 7 0 0 0 7 7z"/></svg>
       * Shield Alert: <svg class="medical-chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
       * Salad / Diet: <svg class="medical-chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/><path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/></svg>
       * Heart / Pulse: <svg class="medical-chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
       * Pill / Medicine: <svg class="medical-chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="9" width="20" height="6" rx="3" transform="rotate(-45 12 12)"/><line x1="7.5" y1="16.5" x2="16.5" y2="7.5"/></svg>
       * Brain: <svg class="medical-chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M12 6v12M8 10h8M9 14h6" opacity="0.4"/></svg>
       Keep SVGs extremely clean and lightweight, wrapping them inline in markdown paragraphs.
    6. Response Length Control:
       - Brief/Casual queries (greetings like "Hi", "Hello", "How are you", or thanks like "Thank you", "Thanks", "Aabhar", "Dhanyawad", "Shukriya") MUST receive a brief, warm response (1 to 2 sentences) in the active language, with no disclaimers.
    7. Dynamic Disclaimers:
       - Follow the medical disclaimer instructions defined above. Do NOT append disclaimers to casual chit-chat, only to medical or clinical queries.

    Patient's Report Data (if any):
    ---
    {report_text}
    ---

    Conversation History:
    ---
    {history_str}
    ---

    Patient's Question:
    "{question}"
    """
    
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
    except Exception as e:
        raise RuntimeError(f"Connection to Gemini REST API failed: {str(e)}")
        
    if response.status_code != 200:
        raise ValueError(f"Invalid response from Gemini API (status code {response.status_code}): {response.text}")
        
    try:
        response_json = response.json()
    except Exception as e:
        raise ValueError(f"Invalid response from Gemini API (failed to parse JSON): {str(e)}")
        
    candidates = response_json.get("candidates")
    if not candidates or len(candidates) == 0:
        raise ValueError(f"No candidates returned from Gemini API. Full response: {response_json}")
        
    candidate = candidates[0]
    content = candidate.get("content")
    if not content:
        raise ValueError("Invalid response structure: 'content' field missing in candidate.")
        
    parts = content.get("parts")
    if not parts or len(parts) == 0:
        raise ValueError("Invalid response structure: 'parts' field missing or empty in candidate content.")
        
    text = parts[0].get("text")
    if not text:
        raise ValueError("Invalid response structure: 'text' field missing in candidate content parts.")
        
    # Store in session memory
    conversation_history.append({"role": "User", "content": question})
    conversation_history.append({"role": "AI", "content": text})

    return text



def analyze_xray_image(image_path):
    """
    Analyzes an X-ray or diagnostic image using the Gemini multimodal API.
    Returns a dictionary with detections, confidence, summary, diet, exercise, medicines, lifestyle, and recommendation.
    """
    import base64
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing from environment or .env file.")
    
    # Read and encode image file
    try:
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to read image file: {str(e)}")
        
    # Determine MIME type based on file extension
    ext = os.path.splitext(image_path)[1].lower()
    if ext == ".png":
        mime_type = "image/png"
    elif ext in [".jpg", ".jpeg"]:
        mime_type = "image/jpeg"
    elif ext == ".avif":
        mime_type = "image/avif"
    else:
        mime_type = "image/jpeg" # fallback
        
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    prompt = """
    You are an expert Clinical Radiologist and AI assistant. Analyze this diagnostic scan or X-ray image.
    
    CRITICAL TONE & VERBOSITY SAFETY INSTRUCTIONS:
    - Never present any finding or diagnosis as absolute, sure, or confirmed. Frame all findings as potential, possible, or observed features needing clinical correlation.
    - DO NOT use alarmist, aggressive, or panic-inducing wording. You must strictly avoid the following blacklisted terms:
      * "emergency" -> instead use "clinical evaluation recommended"
      * "high risk" / "critical" / "severe" -> instead use "specialist consultation advised"
      * "do not delay" / "immediate" / "at once" / "urgently" -> instead use "further assessment may be beneficial" or "prompt follow-up is recommended"
      * "diagnosed" / "diagnose" / "diagnosing" -> instead use "identified feature", "observed pattern", or "potential indication"
    - Friendly Clinical Tone: Write with a warm, caring, reassuring clinical doctor tone.
    - Detailed Presentation: Mix a descriptive introductory paragraph (1-2 sentences) explaining the status/findings with 2 to 4 detailed but readable bullet points.
    - Medical Emojis & Inline SVGs: Integrate appropriate medical emojis naturally. Also, embed a small, lightweight inline SVG medical icon near the beginning of each markdown field.
      * For Scan Findings, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4.82 4.82A9 9 0 0 0 12 19.08V22h3v-2.92A9 9 0 0 0 20.3 7.7"/><circle cx="12" cy="11" r="3"/></svg>
      * For Concerns, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      * For Steps, use: <svg class="medical-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
    
    DYNAMIC REALISTIC ANALYSIS RULES:
    - Avoid generic medical templates, placeholders, or copy-pasted advice. Do NOT invent or default to suggesting anemia, blood sugar issues, or high cholesterol unless they are explicitly present or logical from this scan/image.
    - Custom-tailor findings, concerns, and steps to the specific details observed in the scan. If a specific category is not indicated or relevant based on the scan, you MUST return exactly one single, natural bullet point confirming this (e.g., "* No visual anomalies are observed in this scan.").

    You must return a valid JSON object containing the analysis. The JSON must contain exactly these four keys:
    1. "scan_findings": A summary of findings, anatomical features, and observations (include suggested visual confidence metric). Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated. Decorated with the Stethoscope inline SVG.
    2. "potential_concerns": Potential anomalies, abnormal parameters, or potential pathologies identified. Use cautious clinical phrasing. Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated. Decorated with the Shield Alert inline SVG.
    3. "suggested_steps": Concise physical activity, lifestyle suggestions, or follow-up advice. Mix a short intro paragraph + exactly 2 to 4 detailed markdown bullet points starting with *; or exactly 1 bullet point if not indicated. Decorated with the Heart Rate / Activity inline SVG.
    4. "doctor_recommendation": Medically responsible recommendations. Keep it to 1 or 2 cautious, professional sentences (do not use bullets here).

    Formatting rules for the JSON values:
    - Keys 1, 2, and 3 must contain list items starting with "* ".
    - If the category has findings/recommendations, provide exactly 2 to 4 short markdown bullet points (max 12 words per bullet point).
    - If the category is not relevant or has no findings, provide exactly 1 single markdown bullet point (max 12 words) stating this.
    - Keep bullet points short, clear, and professional.
    - Respond ONLY with the JSON object. Do not wrap the JSON in markdown code blocks like ```json ... ```.
    """
    
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    },
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": image_data
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
    except Exception as e:
        raise RuntimeError(f"Connection to Gemini REST API failed: {str(e)}")
        
    if response.status_code != 200:
        raise ValueError(f"Invalid response from Gemini API (status code {response.status_code}): {response.text}")
        
    try:
        response_json = response.json()
    except Exception as e:
        raise ValueError(f"Invalid response from Gemini API (failed to parse JSON): {str(e)}")
        
    candidates = response_json.get("candidates")
    if not candidates or len(candidates) == 0:
        raise ValueError(f"No candidates returned from Gemini API. Full response: {response_json}")
        
    candidate = candidates[0]
    content = candidate.get("content")
    if not content:
        raise ValueError("Invalid response structure: 'content' field missing in candidate.")
        
    parts = content.get("parts")
    if not parts or len(parts) == 0:
        raise ValueError("Invalid response structure: 'parts' field missing or empty in candidate content.")
        
    text = parts[0].get("text")
    if not text:
        raise ValueError("Invalid response structure: 'text' field missing in candidate content parts.")
        
    text = text.strip()
    
    # Strip markdown wrapper if present
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        
    parsed_data = parse_json_safely(text)
    if parsed_data:
        # Ensure all keys are present and cleaned
        parsed_data["scan_findings"] = clean_raw_text_fallback(parsed_data.get("scan_findings", ""))
        parsed_data["potential_concerns"] = clean_raw_text_fallback(parsed_data.get("potential_concerns", ""))
        parsed_data["suggested_steps"] = clean_raw_text_fallback(parsed_data.get("suggested_steps", ""))
        parsed_data["doctor_recommendation"] = clean_raw_text_fallback(parsed_data.get("doctor_recommendation", ""))
        
        # Populate old keys for compatibility
        parsed_data["detections"] = parsed_data.get("scan_findings", "").split("\n")
        parsed_data["confidence"] = "N/A"
        parsed_data["summary"] = parsed_data.get("scan_findings", "")
        parsed_data["diet"] = ""
        parsed_data["exercise"] = ""
        parsed_data["medicines"] = ""
        parsed_data["lifestyle"] = ""
        parsed_data["recommendation"] = parsed_data.get("doctor_recommendation", "")
        
        return parsed_data
    else:
        # Fallback if AI output is not valid JSON
        cleaned_text = clean_raw_text_fallback(text)
        return {
            "scan_findings": cleaned_text,
            "potential_concerns": "* Possible abnormality detected. Specialist consultation advised.",
            "suggested_steps": "* Further assessment may be beneficial.",
            "doctor_recommendation": "Clinical evaluation recommended. Consult your physician for confirmatory scans.",
            "detections": [cleaned_text],
            "confidence": "N/A",
            "summary": cleaned_text,
            "diet": "Clinical evaluation recommended.",
            "exercise": "Specialist consultation advised.",
            "medicines": "Further assessment may be beneficial.",
            "lifestyle": "Clinical evaluation recommended.",
            "recommendation": "Clinical evaluation recommended. Consult your physician for confirmatory scans."
        }