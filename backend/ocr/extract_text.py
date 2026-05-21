import fitz
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat
import base64
import io
import os
import requests

# Register AVIF support via pillow-avif-plugin (pip install pillow-avif-plugin)
try:
    import pillow_avif  # noqa: F401  — side-effect: registers AVIF codec with Pillow
except ImportError:
    pass  # AVIF uploads will fail gracefully if plugin not installed

# Tesseract path
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def extract_text_from_pdf(pdf_path):
    text = ""

    pdf = fitz.open(pdf_path)

    for page in pdf:
        page_text = page.get_text()
        if page_text:
            text += page_text + "\n"

    # Fallback to OCR if extracted text is too short (e.g. scanned/image-only PDF)
    if len(text.strip()) < 50:
        ocr_text_parts = []
        custom_config = r'--oem 3 --psm 6'

        for page in pdf:
            # Render page to high-quality image (2x zoom for clarity)
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            
            # Convert PyMuPDF pixmap to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Preprocess image (Grayscale -> Contrast Enhancement -> Sharpen)
            gray = ImageOps.grayscale(img)
            contrast_enhancer = ImageEnhance.Contrast(gray)
            contrasted = contrast_enhancer.enhance(2.5)
            sharpened = contrasted.filter(ImageFilter.SHARPEN)
            
            try:
                # Run Tesseract OCR on the page
                page_ocr_text = pytesseract.image_to_string(sharpened, config=custom_config)
            except Exception as e:
                print(f"Tesseract OCR page extraction failed, falling back to Gemini: {e}")
                page_ocr_text = extract_text_via_gemini(sharpened)
            
            if page_ocr_text:
                ocr_text_parts.append(page_ocr_text)
        
        text = "\n".join(ocr_text_parts)

    pdf.close()
    return text


def preprocess_image_for_ocr(image):
    """
    Preprocesses the PIL Image to improve OCR accuracy for handwriting:
    - Grayscale conversion
    - Resize upscaling
    - Autocontrast normalization
    - Contrast enhancement
    - Sharpening
    - Dynamic threshold binarization
    """
    # 1. Grayscale
    gray = ImageOps.grayscale(image)
    
    # 2. Resize by 2x if the image is relatively small (helps OCR)
    w, h = gray.size
    if w < 1500 or h < 1500:
        gray = gray.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
    
    # 3. Autocontrast (normalizes lighting across image)
    gray = ImageOps.autocontrast(gray)

    # 4. Increase Contrast
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(3.0)  # Enhanced factor for better handwriting stroke separation
    
    # 5. Sharpen
    sharpened = enhanced.filter(ImageFilter.SHARPEN)
    # Apply a secondary light unsharp mask for cleaner borders
    sharpened = sharpened.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    
    # 6. Dynamic Thresholding (Binarization) based on average brightness
    stat = ImageStat.Stat(sharpened)
    mean_brightness = stat.mean[0]
    
    # Text is usually darker than the paper. Set a threshold below mean brightness to segment it.
    threshold = int(mean_brightness * 0.82)
    threshold = max(50, min(threshold, 205))  # Keep it in a sane range
    
    binarized = sharpened.point(lambda p: 255 if p > threshold else 0)
    
    return binarized


def extract_text_via_gemini(image_input):
    """
    Sends the image (either PIL Image or file path) to Gemini for text extraction (multimodal OCR fallback).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Gemini API Key missing - OCR fallback unavailable.")
        return ""

    if isinstance(image_input, str):
        try:
            with open(image_input, "rb") as f:
                image_bytes = f.read()
            ext = os.path.splitext(image_input)[1].lower()
            if ext == ".png":
                mime_type = "image/png"
            elif ext in [".jpg", ".jpeg"]:
                mime_type = "image/jpeg"
            elif ext == ".avif":
                mime_type = "image/avif"
            else:
                mime_type = "image/png"
        except Exception as e:
            print(f"Error reading image path for Gemini OCR: {e}")
            return ""
    else:
        try:
            buf = io.BytesIO()
            image_input.save(buf, format="PNG")
            image_bytes = buf.getvalue()
            mime_type = "image/png"
        except Exception as e:
            print(f"Error converting PIL image for Gemini OCR: {e}")
            return ""

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    prompt = "Perform OCR on this image. Extract all text from it exactly as it is, without adding any introduction, comments, or extra markdown formatting. Just output the extracted text."
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": encoded_image
                        }
                    }
                ]
            }
        ]
    }
    
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        if response.status_code == 200:
            res_json = response.json()
            return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"Gemini OCR fallback failed: {e}")
    return ""


def extract_text_from_image(image_path):
    try:
        image = Image.open(image_path)
        # Apply preprocessing to improve handwritten/printed text recognition
        preprocessed_image = preprocess_image_for_ocr(image)
        text = pytesseract.image_to_string(preprocessed_image)
        return text
    except Exception as e:
        print(f"Tesseract OCR image extraction failed, falling back to Gemini: {e}")
        return extract_text_via_gemini(image_path)