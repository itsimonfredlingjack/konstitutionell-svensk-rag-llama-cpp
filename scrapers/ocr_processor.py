#!/usr/bin/env python3
"""
Smart OCR Processor for Constitutional AI
Automatically detects if PDF is digital or scanned and uses appropriate extraction method.

Features:
- Digital PDF: Fast PyMuPDF text extraction
- Scanned PDF: PaddleOCR with GPU acceleration
- Hybrid PDFs: Automatic per-page detection
- Swedish language optimized
"""

import io
import logging
from pathlib import Path
from typing import Union

import fitz  # PyMuPDF
from PIL import Image

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SmartPDFExtractor:
    """
    Intelligent PDF text extractor with automatic OCR fallback.

    Usage:
        extractor = SmartPDFExtractor()
        result = extractor.extract_text("document.pdf")
        print(result['text'])
    """

    def __init__(self, use_gpu: bool = True, lang: str = "en"):
        """
        Initialize the extractor.

        Args:
            use_gpu: Enable GPU acceleration for OCR (requires CUDA)
            lang: OCR language ('en' for multilingual including Swedish)
        """
        self.use_gpu = use_gpu
        self.lang = lang
        self._ocr = None  # Lazy load OCR engine

        logger.info(f"SmartPDFExtractor initialized (GPU: {use_gpu}, Lang: {lang})")

    @property
    def ocr(self):
        """Lazy load PaddleOCR only when needed."""
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR

                logger.info("Loading PaddleOCR engine...")
                # PaddleOCR 3.x API
                device = "gpu:0" if self.use_gpu else "cpu"
                self._ocr = PaddleOCR(
                    use_angle_cls=True,  # Detect text rotation
                    lang=self.lang,
                    device=device,
                )
                logger.info("✓ PaddleOCR loaded successfully")
            except ImportError:
                logger.error(
                    "PaddleOCR not installed! Install with: pip install paddlepaddle paddleocr"
                )
                raise
        return self._ocr

    def is_page_scanned(self, page, threshold: int = 50) -> bool:
        """
        Detect if a PDF page is scanned (image-based) or digital (text-based).

        Args:
            page: PyMuPDF page object
            threshold: Minimum characters to consider page as digital

        Returns:
            True if page appears to be scanned, False if digital
        """
        text = page.get_text().strip()
        return len(text) < threshold

    def extract_text_digital(self, page) -> str:
        """Extract text from digital PDF page using PyMuPDF."""
        return page.get_text()

    def extract_text_ocr(self, page) -> str:
        """
        Extract text from scanned PDF page using PaddleOCR.

        Args:
            page: PyMuPDF page object

        Returns:
            Extracted text from OCR
        """
        # Convert PDF page to image
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x resolution for better OCR
        img_bytes = pix.tobytes("png")

        # Run OCR
        result = self.ocr.ocr(img_bytes, cls=True)

        if not result or not result[0]:
            return ""

        # Extract text from OCR result
        # PaddleOCR returns: [[[bbox], (text, confidence)], ...]
        lines = []
        for line in result[0]:
            if line and len(line) >= 2:
                text, confidence = line[1]
                if confidence > 0.5:  # Only include high-confidence results
                    lines.append(text)

        return "\n".join(lines)

    def extract_text(self, pdf_path: Union[str, Path], auto_detect: bool = True) -> dict:
        """
        Extract text from PDF with automatic digital/scanned detection.

        Args:
            pdf_path: Path to PDF file
            auto_detect: Automatically detect if OCR is needed per page

        Returns:
            Dictionary with:
                - text: Extracted text
                - pages: Number of pages
                - digital_pages: Pages extracted digitally
                - ocr_pages: Pages extracted with OCR
                - method: 'digital', 'ocr', or 'hybrid'
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info(f"Processing: {pdf_path.name}")

        doc = fitz.open(pdf_path)
        text_parts = []
        digital_count = 0
        ocr_count = 0
        total_pages = len(doc)

        for page_num in range(total_pages):
            page = doc[page_num]

            if auto_detect and self.is_page_scanned(page):
                # Scanned page - use OCR
                logger.info(f"  Page {page_num + 1}/{total_pages}: OCR (scanned)")
                text = self.extract_text_ocr(page)
                ocr_count += 1
            else:
                # Digital page - use PyMuPDF
                logger.info(f"  Page {page_num + 1}/{total_pages}: Digital text")
                text = self.extract_text_digital(page)
                digital_count += 1

            if text.strip():
                text_parts.append(f"--- Page {page_num + 1} ---\n{text}")

        doc.close()

        # Determine extraction method
        if ocr_count == 0:
            method = "digital"
        elif digital_count == 0:
            method = "ocr"
        else:
            method = "hybrid"

        result = {
            "text": "\n\n".join(text_parts),
            "pages": total_pages,
            "digital_pages": digital_count,
            "ocr_pages": ocr_count,
            "method": method,
            "file": str(pdf_path),
        }

        logger.info(
            f"✓ Extracted {len(result['text'])} chars ({method}: {digital_count} digital, {ocr_count} OCR)"
        )

        return result

    def extract_images(self, pdf_path: Union[str, Path]) -> list[Image.Image]:
        """
        Extract all images from PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of PIL Image objects
        """
        pdf_path = Path(pdf_path)
        doc = fitz.open(pdf_path)
        images = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()

            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]

                # Convert to PIL Image
                image = Image.open(io.BytesIO(image_bytes))
                images.append(image)

        doc.close()
        logger.info(f"Extracted {len(images)} images from {pdf_path.name}")

        return images


class BatchPDFProcessor:
    """Process multiple PDFs in batch with progress tracking."""

    def __init__(self, use_gpu: bool = True):
        self.extractor = SmartPDFExtractor(use_gpu=use_gpu)
        self.results = []

    def process_directory(self, directory: Union[str, Path], pattern: str = "*.pdf") -> list[dict]:
        """
        Process all PDFs in a directory.

        Args:
            directory: Path to directory containing PDFs
            pattern: Glob pattern for PDF files

        Returns:
            List of extraction results
        """
        directory = Path(directory)
        pdf_files = list(directory.glob(pattern))

        logger.info(f"Found {len(pdf_files)} PDF files in {directory}")

        for i, pdf_path in enumerate(pdf_files, 1):
            logger.info(f"\n[{i}/{len(pdf_files)}] Processing {pdf_path.name}")

            try:
                result = self.extractor.extract_text(pdf_path)
                self.results.append(result)
            except Exception as e:
                logger.error(f"Error processing {pdf_path.name}: {e}")
                self.results.append(
                    {"file": str(pdf_path), "error": str(e), "text": "", "pages": 0}
                )

        return self.results

    def get_summary(self) -> dict:
        """Get processing summary statistics."""
        total_pages = sum(r.get("pages", 0) for r in self.results)
        total_chars = sum(len(r.get("text", "")) for r in self.results)
        digital_pages = sum(r.get("digital_pages", 0) for r in self.results)
        ocr_pages = sum(r.get("ocr_pages", 0) for r in self.results)
        errors = sum(1 for r in self.results if "error" in r)

        return {
            "total_files": len(self.results),
            "total_pages": total_pages,
            "total_characters": total_chars,
            "digital_pages": digital_pages,
            "ocr_pages": ocr_pages,
            "errors": errors,
            "success_rate": (len(self.results) - errors) / len(self.results) * 100
            if self.results
            else 0,
        }


# CLI interface
if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python ocr_processor.py <pdf_file_or_directory>")
        print("\nExamples:")
        print("  python ocr_processor.py document.pdf")
        print("  python ocr_processor.py /path/to/pdfs/")
        sys.exit(1)

    path = Path(sys.argv[1])

    if path.is_file():
        # Single file
        extractor = SmartPDFExtractor(use_gpu=True)
        result = extractor.extract_text(path)

        print("\n" + "=" * 80)
        print("EXTRACTION RESULT")
        print("=" * 80)
        print(f"File: {result['file']}")
        print(f"Pages: {result['pages']}")
        print(f"Method: {result['method']}")
        print(f"Digital pages: {result['digital_pages']}")
        print(f"OCR pages: {result['ocr_pages']}")
        print(f"Characters: {len(result['text']):,}")
        print("\n" + "-" * 80)
        print("TEXT PREVIEW (first 500 chars):")
        print("-" * 80)
        print(result["text"][:500])

        # Save to file
        output_file = path.with_suffix(".txt")
        output_file.write_text(result["text"], encoding="utf-8")
        print(f"\n✓ Full text saved to: {output_file}")

    elif path.is_dir():
        # Batch processing
        processor = BatchPDFProcessor(use_gpu=True)
        results = processor.process_directory(path)
        summary = processor.get_summary()

        print("\n" + "=" * 80)
        print("BATCH PROCESSING SUMMARY")
        print("=" * 80)
        print(f"Files processed: {summary['total_files']}")
        print(f"Total pages: {summary['total_pages']}")
        print(f"Digital pages: {summary['digital_pages']}")
        print(f"OCR pages: {summary['ocr_pages']}")
        print(f"Total characters: {summary['total_characters']:,}")
        print(f"Errors: {summary['errors']}")
        print(f"Success rate: {summary['success_rate']:.1f}%")

        # Save results
        output_file = path / "ocr_results.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)

        print(f"\n✓ Results saved to: {output_file}")
    else:
        print(f"Error: {path} is not a file or directory")
        sys.exit(1)
