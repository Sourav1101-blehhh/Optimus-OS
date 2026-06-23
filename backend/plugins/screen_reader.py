import pytesseract
from PIL import ImageGrab
import os

PLUGIN_METADATA = {
    "name": "screen_reader",
    "description": "Captures the screen and extracts text using OCR. Only use when asked to read the screen.",
    "keywords": ["read screen", "ocr", "extract text from screen", "what does the screen say"]
}

def execute(args: dict = None) -> str:
    try:
        # Check if tesseract is installed
        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError:
            # Try to find it in common windows locations
            if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
                pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            else:
                return "OCR Failed: Tesseract-OCR is not installed or not in PATH."
                
        img = ImageGrab.grab()
        text = pytesseract.image_to_string(img)
        if not text.strip():
            return "No readable text found on the screen."
        return f"Text extracted from screen:\n\n{text}"
    except Exception as e:
        return f"OCR Failed: {e}"
