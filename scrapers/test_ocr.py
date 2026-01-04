#!/usr/bin/env python3
"""
Test script for OCR processor
Tests both digital and scanned PDF extraction
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ocr_processor import BatchPDFProcessor, SmartPDFExtractor


def test_single_pdf():
    """Test single PDF extraction"""
    print("=" * 80)
    print("TEST 1: Single PDF Extraction")
    print("=" * 80)

    # Create test PDF path (you can change this)
    test_pdf = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/jo_pdfs")

    if not test_pdf.exists():
        print(f"⚠️  Test directory not found: {test_pdf}")
        print("Creating a simple test...")
        return test_digital_text()

    # Find first PDF
    pdf_files = list(test_pdf.glob("*.pdf"))
    if not pdf_files:
        print(f"⚠️  No PDF files found in {test_pdf}")
        return

    test_file = pdf_files[0]
    print(f"\nTesting with: {test_file.name}")

    extractor = SmartPDFExtractor(use_gpu=True)
    result = extractor.extract_text(test_file)

    print("\n✓ Extraction complete!")
    print(f"  Method: {result['method']}")
    print(f"  Pages: {result['pages']}")
    print(f"  Digital pages: {result['digital_pages']}")
    print(f"  OCR pages: {result['ocr_pages']}")
    print(f"  Characters extracted: {len(result['text']):,}")

    print("\n" + "-" * 80)
    print("TEXT PREVIEW (first 300 chars):")
    print("-" * 80)
    print(result["text"][:300])
    print("...")


def test_digital_text():
    """Test with a simple digital PDF"""
    print("\n" + "=" * 80)
    print("TEST 2: Digital PDF Test")
    print("=" * 80)

    # Create a simple test PDF with PyMuPDF
    import fitz

    test_file = Path("/tmp/test_digital.pdf")
    doc = fitz.open()
    page = doc.new_page()

    # Add Swedish text
    text = """
    TESTDOKUMENT

    Detta är ett test av PDF-extraktion för Constitutional AI.

    Systemet ska kunna:
    1. Extrahera text från digitala PDF:er (som denna)
    2. Använda OCR för skannade dokument
    3. Automatiskt välja rätt metod

    Svenska tecken: åäö ÅÄÖ

    Lagar: SFS 1994:200, Regeringsformen 1 kap. 1 §
    """

    page.insert_text((50, 50), text, fontsize=12)
    doc.save(test_file)
    doc.close()

    print(f"Created test PDF: {test_file}")

    # Extract
    extractor = SmartPDFExtractor(use_gpu=True)
    result = extractor.extract_text(test_file)

    print("\n✓ Extraction complete!")
    print(f"  Method: {result['method']}")
    print(f"  Pages: {result['pages']}")
    print(f"  Characters: {len(result['text']):,}")

    print("\n" + "-" * 80)
    print("EXTRACTED TEXT:")
    print("-" * 80)
    print(result["text"])

    # Cleanup
    test_file.unlink()
    print("\n✓ Test file removed")


def test_batch_processing():
    """Test batch processing"""
    print("\n" + "=" * 80)
    print("TEST 3: Batch Processing")
    print("=" * 80)

    test_dir = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/jo_pdfs")

    if not test_dir.exists():
        print(f"⚠️  Test directory not found: {test_dir}")
        print("Skipping batch test")
        return

    pdf_files = list(test_dir.glob("*.pdf"))
    if not pdf_files:
        print("⚠️  No PDF files found")
        return

    # Limit to first 3 PDFs for testing
    print(f"Found {len(pdf_files)} PDFs, testing first 3...")

    processor = BatchPDFProcessor(use_gpu=True)

    # Process only first 3
    for pdf in pdf_files[:3]:
        print(f"\nProcessing: {pdf.name}")
        try:
            result = processor.extractor.extract_text(pdf)
            processor.results.append(result)
        except Exception as e:
            print(f"  Error: {e}")

    summary = processor.get_summary()

    print("\n" + "=" * 80)
    print("BATCH SUMMARY")
    print("=" * 80)
    print(f"Files processed: {summary['total_files']}")
    print(f"Total pages: {summary['total_pages']}")
    print(f"Digital pages: {summary['digital_pages']}")
    print(f"OCR pages: {summary['ocr_pages']}")
    print(f"Total characters: {summary['total_characters']:,}")
    print(f"Success rate: {summary['success_rate']:.1f}%")


def test_gpu_availability():
    """Test if GPU is available for PaddleOCR"""
    print("\n" + "=" * 80)
    print("TEST 4: GPU Availability")
    print("=" * 80)

    try:
        import paddle

        print(f"PaddlePaddle version: {paddle.__version__}")
        print(f"GPU available: {paddle.is_compiled_with_cuda()}")

        if paddle.is_compiled_with_cuda():
            print(f"GPU count: {paddle.device.cuda.device_count()}")
            print(f"Current device: {paddle.device.get_device()}")
        else:
            print("⚠️  Running on CPU (slower)")
    except Exception as e:
        print(f"Error checking GPU: {e}")


if __name__ == "__main__":
    print("\n" + "🔬 " * 20)
    print("OCR PROCESSOR TEST SUITE")
    print("🔬 " * 20)

    # Run tests
    test_gpu_availability()
    test_digital_text()

    # Optional: test with real PDFs if available
    if len(sys.argv) > 1:
        test_pdf_path = Path(sys.argv[1])
        if test_pdf_path.is_file():
            print(f"\n\nTesting with provided file: {test_pdf_path}")
            extractor = SmartPDFExtractor(use_gpu=True)
            result = extractor.extract_text(test_pdf_path)
            print(f"\n✓ Method: {result['method']}")
            print(
                f"✓ Pages: {result['pages']} ({result['digital_pages']} digital, {result['ocr_pages']} OCR)"
            )
            print(f"✓ Characters: {len(result['text']):,}")
        elif test_pdf_path.is_dir():
            print(f"\n\nBatch testing directory: {test_pdf_path}")
            test_batch_processing()
    else:
        test_single_pdf()

    print("\n" + "=" * 80)
    print("✅ ALL TESTS COMPLETE")
    print("=" * 80)
    print("\nUsage:")
    print("  python test_ocr.py                    # Run default tests")
    print("  python test_ocr.py document.pdf       # Test specific PDF")
    print("  python test_ocr.py /path/to/pdfs/     # Batch test directory")
