# OCR Support for Constitutional AI

## Overview

Constitutional AI now has **OCR (Optical Character Recognition)** support for processing scanned documents and images. The system automatically detects whether a PDF is digital or scanned and uses the appropriate extraction method.

## Features

✅ **Hybrid PDF Processing**
- Digital PDFs: Fast PyMuPDF text extraction
- Scanned PDFs: PaddleOCR with GPU acceleration
- Automatic per-page detection

✅ **GPU Accelerated**
- Uses RTX 4070 for fast OCR processing
- Fallback to CPU if GPU unavailable

✅ **Swedish Language Support**
- Multilingual OCR model includes Swedish
- Handles Swedish characters (åäö ÅÄÖ)

## Installation

### Quick Install
```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
source venv/bin/activate
pip install -r scrapers/requirements_ocr.txt
```

### Manual Install
```bash
pip install PyMuPDF Pillow
pip install paddlepaddle-gpu paddleocr
pip install 'langchain<0.3.0'  # Compatibility fix
```

## Usage

### Basic Usage

```python
from ocr_processor import SmartPDFExtractor

# Initialize extractor
extractor = SmartPDFExtractor(use_gpu=True)

# Extract text from PDF
result = extractor.extract_text("document.pdf")

print(f"Method: {result['method']}")  # 'digital', 'ocr', or 'hybrid'
print(f"Pages: {result['pages']}")
print(f"Text: {result['text']}")
```

### Batch Processing

```python
from ocr_processor import BatchPDFProcessor

# Process directory of PDFs
processor = BatchPDFProcessor(use_gpu=True)
results = processor.process_directory("/path/to/pdfs/")

# Get summary
summary = processor.get_summary()
print(f"Processed: {summary['total_files']} files")
print(f"Digital pages: {summary['digital_pages']}")
print(f"OCR pages: {summary['ocr_pages']}")
```

### Command Line

```bash
# Single file
python ocr_processor.py document.pdf

# Batch processing
python ocr_processor.py /path/to/pdfs/

# Run tests
python test_ocr.py
```

## How It Works

### 1. Automatic Detection

For each PDF page:
1. Try to extract text with PyMuPDF
2. If text < 50 characters → **Scanned page** → Use OCR
3. If text ≥ 50 characters → **Digital page** → Use PyMuPDF

### 2. OCR Process (for scanned pages)

```
PDF Page → Convert to Image (2x resolution)
         → PaddleOCR (GPU accelerated)
         → Extract text with confidence > 0.5
         → Return structured text
```

### 3. Output Format

```python
{
    'text': "Extracted text...",
    'pages': 10,
    'digital_pages': 8,
    'ocr_pages': 2,
    'method': 'hybrid',  # 'digital', 'ocr', or 'hybrid'
    'file': '/path/to/document.pdf'
}
```

## Performance

| Method | Speed | Accuracy | Use Case |
|--------|-------|----------|----------|
| **Digital** | ⚡ Very Fast (< 1s/page) | 100% | Born-digital PDFs |
| **OCR** | 🐢 Slower (2-5s/page) | 85-95% | Scanned documents |
| **Hybrid** | ⚡🐢 Mixed | Mixed | Mixed documents |

## GPU Status

Check if GPU is available:

```python
import paddle
print(f"GPU available: {paddle.is_compiled_with_cuda()}")
print(f"GPU count: {paddle.device.cuda.device_count()}")
```

Expected output on this server:
```
GPU available: True
GPU count: 1
Current device: gpu:0
```

## Known Issues & Workarounds

### Issue: PaddleOCR Version Compatibility

**Problem:** PaddleOCR 3.x has breaking API changes and dependency conflicts.

**Current Status:** 
- ✅ PyMuPDF extraction works perfectly
- ⚠️ PaddleOCR requires version pinning
- ✅ Digital PDFs process without issues

**Workaround:**
```bash
# Use older compatible versions
pip install 'paddleocr==2.7.0' 'paddlepaddle-gpu==2.5.0'
```

### Issue: langchain.docstore Import Error

**Problem:** PaddleX requires old langchain API.

**Solution:**
```bash
pip install 'langchain<0.3.0'
```

## Alternative OCR Engines

If PaddleOCR doesn't work, try these alternatives:

### 1. Tesseract OCR (Traditional, Reliable)

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-swe
pip install pytesseract

# Usage
import pytesseract
from PIL import Image
text = pytesseract.image_to_string(Image.open("scan.png"), lang='swe')
```

### 2. RapidOCR (Lightweight, ONNX)

```bash
pip install rapidocr-onnxruntime

# Usage
from rapidocr_onnxruntime import RapidOCR
ocr = RapidOCR()
result, _ = ocr("scan.png")
```

### 3. EasyOCR (Deep Learning)

```bash
pip install easyocr

# Usage
import easyocr
reader = easyocr.Reader(['sv', 'en'], gpu=True)
result = reader.readtext("scan.png")
```

## Integration with Scrapers

To use OCR in existing scrapers:

```python
# In your scraper
from ocr_processor import SmartPDFExtractor

class MyScraper:
    def __init__(self):
        self.pdf_extractor = SmartPDFExtractor(use_gpu=True)
    
    def process_pdf(self, pdf_url):
        # Download PDF
        pdf_path = self.download_pdf(pdf_url)
        
        # Extract text (auto-detects digital vs scanned)
        result = self.pdf_extractor.extract_text(pdf_path)
        
        return {
            'text': result['text'],
            'method': result['method'],
            'pages': result['pages']
        }
```

## Testing

Run the test suite:

```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers
source ../venv/bin/activate
python test_ocr.py
```

Tests include:
1. ✅ GPU availability check
2. ✅ Digital PDF extraction
3. ⚠️ Scanned PDF OCR (requires version fix)
4. ⚠️ Batch processing (requires version fix)

## Troubleshooting

### OCR is slow
- Check GPU usage: `nvidia-smi`
- Reduce image resolution in `extract_text_ocr()`
- Use batch processing for multiple files

### Low accuracy
- Increase image resolution (currently 2x)
- Adjust confidence threshold (currently 0.5)
- Try different OCR engine (Tesseract, EasyOCR)

### Out of memory
- Reduce batch size
- Process pages individually
- Use CPU instead of GPU

## Future Improvements

- [ ] Fix PaddleOCR version compatibility
- [ ] Add support for image files (PNG, JPG)
- [ ] Implement table extraction
- [ ] Add language auto-detection
- [ ] Create REST API endpoint for OCR
- [ ] Integrate with Constitutional GPT frontend

## Files

```
scrapers/
├── ocr_processor.py          # Main OCR processor
├── test_ocr.py               # Test suite
├── requirements_ocr.txt      # OCR dependencies
└── README_OCR.md             # This file
```

## Support

For issues or questions:
1. Check this README
2. Run `python test_ocr.py` to diagnose
3. Check GPU with `nvidia-smi`
4. Review logs in console output

---

**Status:** ✅ Installed, ⚠️ Requires version pinning for full OCR support

**Last Updated:** 2024-12-22
