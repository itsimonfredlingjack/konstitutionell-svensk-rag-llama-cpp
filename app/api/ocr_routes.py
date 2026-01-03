"""
OCR Routes - Document Upload and Text Extraction
Uses IBM Granite Docling 258M via llama.cpp for document OCR
GPT-OSS 20B via llama-server for answering questions

Architecture:
- Granite Docling: Runs on CPU + GPU vision encoder (~500MB)
- GPT-OSS: Runs on llama-server:8080 (~11GB VRAM)
- Both can run simultaneously - NO HOTSWAP NEEDED!
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List
import httpx
import subprocess
import tempfile
import os
import re
from pathlib import Path
from datetime import datetime
import asyncio

router = APIRouter(prefix="/api/ocr", tags=["ocr"])

# Model paths
GRANITE_MODEL = "/home/ai-server/models/granite-docling/granite-docling-258M-f16.gguf"
GRANITE_MMPROJ = "/home/ai-server/models/granite-docling/mmproj-granite-docling-258M-f16.gguf"
LLAMA_MTMD_CLI = "/home/ai-server/llama.cpp/build/bin/llama-mtmd-cli"

# llama-server for GPT-OSS
LLAMA_SERVER_URL = "http://localhost:8080"

# Supported file types
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


class OCRResponse(BaseModel):
    extracted_text: str
    processing_time_ms: int
    model_used: str
    filename: str


class OCRWithAnswerResponse(BaseModel):
    extracted_text: str
    answer: str
    question: str
    processing_time_ms: int
    ocr_model: str
    answer_model: str
    filename: str


def parse_doctags(doctags_output: str) -> str:
    """
    Parse DocTags XML format to plain text.
    Extracts text content from tags like <text>, <section_header_level_1>, etc.
    """
    if not doctags_output:
        return ""

    # Remove location tags like <loc_123>
    text = re.sub(r'<loc_\d+>', '', doctags_output)

    # Extract content from various DocTags elements
    patterns = [
        (r'<section_header_level_1>(.*?)</section_header_level_1>', r'\n## \1\n'),
        (r'<section_header_level_2>(.*?)</section_header_level_2>', r'\n### \1\n'),
        (r'<text>(.*?)</text>', r'\1\n'),
        (r'<page_header>(.*?)</page_header>', r''),  # Skip page headers
        (r'<page_footer>(.*?)</page_footer>', r''),  # Skip page footers
        (r'<fcel>(.*?)<nl>', r'\1\n'),  # Table cells
        (r'<fcel>(.*?)</fcel>', r'\1 | '),  # Table cells without newline
    ]

    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text, flags=re.DOTALL)

    # Remove remaining tags
    text = re.sub(r'<[^>]+>', '', text)

    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


async def run_granite_ocr(image_path: str) -> str:
    """
    Run Granite Docling OCR on an image file.
    Uses llama-mtmd-cli subprocess for multimodal inference.
    """
    cmd = [
        LLAMA_MTMD_CLI,
        "-m", GRANITE_MODEL,
        "--mmproj", GRANITE_MMPROJ,
        "--image", image_path,
        "-p", "Convert this document to docling format.",
        "--temp", "0",
        "--n-gpu-layers", "999",  # Use GPU for vision encoder
        "--no-warmup",  # Skip warmup for faster response
    ]

    try:
        # Run subprocess asynchronously
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=120.0  # 2 minute timeout
        )

        output = stdout.decode('utf-8', errors='ignore')

        # Extract DocTags content (between <doctag> and </doctag>)
        match = re.search(r'<doctag>.*?</doctag>', output, re.DOTALL)
        if match:
            doctags = match.group(0)
            return parse_doctags(doctags)

        # Fallback: return raw output if no DocTags found
        return output.strip()

    except asyncio.TimeoutError:
        raise HTTPException(status_code=500, detail="OCR timeout (>120s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")


async def run_gpt_oss(prompt: str, max_tokens: int = 500) -> str:
    """Run GPT-OSS via llama-server for answering questions"""
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{LLAMA_SERVER_URL}/v1/completions",
            json={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0.7,
            }
        )

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"GPT-OSS failed: {response.text}")

        data = response.json()
        return data.get("choices", [{}])[0].get("text", "").strip()


def pdf_to_images(pdf_path: str, output_dir: str) -> List[str]:
    """Convert PDF pages to PNG images using pdftoppm"""
    try:
        # Use pdftoppm (from poppler-utils)
        base_name = os.path.join(output_dir, "page")
        subprocess.run([
            "pdftoppm", "-png", "-r", "150",
            "-f", "1", "-l", "5",  # First 5 pages
            pdf_path, base_name
        ], check=True, capture_output=True)

        # Find generated images
        images = sorted([
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.startswith("page") and f.endswith(".png")
        ])

        return images

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"PDF conversion failed: {e.stderr.decode()}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF conversion failed: {str(e)}")


@router.post("/extract", response_model=OCRResponse)
async def extract_text(
    file: UploadFile = File(...),
    custom_prompt: Optional[str] = Form(None)
):
    """
    Upload a document (PDF/image) and extract text using Granite Docling OCR.

    Supports: PDF, PNG, JPG, JPEG, WebP, GIF
    Max file size: 50MB
    For PDFs: Processes first 5 pages

    Returns structured text with headers and paragraphs preserved.
    """
    start_time = datetime.now()

    # Validate file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type {ext} not supported. Allowed: {ALLOWED_EXTENSIONS}"
        )

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            if ext == ".pdf":
                # Save PDF temporarily
                pdf_path = os.path.join(tmp_dir, "input.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(content)

                # Convert to images
                images = pdf_to_images(pdf_path, tmp_dir)

                if not images:
                    raise HTTPException(status_code=500, detail="PDF conversion produced no images")

                # OCR each page
                all_text = []
                for i, img_path in enumerate(images):
                    page_text = await run_granite_ocr(img_path)
                    if page_text:
                        all_text.append(f"--- Sida {i+1} ---\n{page_text}")

                extracted_text = "\n\n".join(all_text)
            else:
                # Image file - save temporarily
                img_path = os.path.join(tmp_dir, f"input{ext}")
                with open(img_path, "wb") as f:
                    f.write(content)

                extracted_text = await run_granite_ocr(img_path)

        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

        return OCRResponse(
            extracted_text=extracted_text,
            processing_time_ms=processing_time,
            model_used="granite-docling-258M",
            filename=file.filename
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-and-answer", response_model=OCRWithAnswerResponse)
async def extract_and_answer(
    file: UploadFile = File(...),
    question: str = Form(...)
):
    """
    Upload a document, extract text with Granite Docling OCR, then answer a question.

    Pipeline (NO HOTSWAP - both models run simultaneously):
    1. Granite Docling OCR (CPU + GPU vision encoder, ~500MB)
    2. GPT-OSS answer (llama-server on GPU, ~11GB)

    Total VRAM: ~11.5GB - fits in 12GB RTX 4070!
    """
    start_time = datetime.now()

    # Validate file
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type {ext} not supported. Allowed: {ALLOWED_EXTENSIONS}"
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Step 1: OCR extraction with Granite Docling
            if ext == ".pdf":
                pdf_path = os.path.join(tmp_dir, "input.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(content)

                images = pdf_to_images(pdf_path, tmp_dir)

                all_text = []
                for i, img_path in enumerate(images):
                    page_text = await run_granite_ocr(img_path)
                    if page_text:
                        all_text.append(f"--- Sida {i+1} ---\n{page_text}")

                extracted_text = "\n\n".join(all_text)
            else:
                img_path = os.path.join(tmp_dir, f"input{ext}")
                with open(img_path, "wb") as f:
                    f.write(content)

                extracted_text = await run_granite_ocr(img_path)

        # Step 2: Answer question with GPT-OSS (runs simultaneously!)
        prompt = f"""Du är en svensk dokumentanalytiker. Baserat på följande extraherade dokumenttext, besvara frågan.

DOKUMENTTEXT:
{extracted_text[:6000]}

FRÅGA: {question}

Svara koncist och direkt på svenska."""

        answer = await run_gpt_oss(prompt)

        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

        return OCRWithAnswerResponse(
            extracted_text=extracted_text,
            answer=answer,
            question=question,
            processing_time_ms=processing_time,
            ocr_model="granite-docling-258M",
            answer_model="gpt-oss-20b",
            filename=file.filename
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def ocr_status():
    """Check OCR system status and model availability"""

    # Check Granite Docling model files
    granite_ok = os.path.exists(GRANITE_MODEL) and os.path.exists(GRANITE_MMPROJ)

    # Check llama-server health
    llama_server_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{LLAMA_SERVER_URL}/health")
            llama_server_ok = response.status_code == 200
    except:
        pass

    return {
        "status": "ready" if granite_ok and llama_server_ok else "degraded",
        "ocr_model": {
            "name": "granite-docling-258M",
            "available": granite_ok,
            "type": "llama.cpp multimodal",
            "note": "IBM Granite - runs on CPU + GPU vision encoder"
        },
        "answer_model": {
            "name": "gpt-oss-20b",
            "available": llama_server_ok,
            "type": "llama-server",
            "endpoint": LLAMA_SERVER_URL
        },
        "architecture": {
            "hotswap_required": False,
            "reason": "Granite Docling (258M) fits alongside GPT-OSS (20B) in 12GB VRAM"
        },
        "supported_formats": list(ALLOWED_EXTENSIONS),
        "max_file_size_mb": MAX_FILE_SIZE / (1024 * 1024)
    }
