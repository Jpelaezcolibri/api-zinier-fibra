import os
import logging
import httpx
import uvicorn
import io
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageEnhance

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv()

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
# Render usa la variable 'PORT', no 'API_PORT'
API_PORT = int(os.getenv("PORT", "8001"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_imagen_n8n")

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="API Fibra Óptica (Binario + Mejorado)",
    description="Recibe imagen, mejora iluminación, y reenvía a n8n.",
    version="2.1.0",
)

# Capturar cualquier error 500 y mostrarlo
from fastapi import Request
from fastapi.responses import JSONResponse
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = "".join(traceback.format_exception(None, exc, exc.__traceback__))
    logger.error(f"CRITICAL ERROR: {error_msg}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "trace": error_msg},
    )

# ── Middleware CORS (Vital para Netlify/Frontend) ───────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir todo para evitar problemas de CORS en pruebas
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Helper: Mejorar Imagen ──────────────────────────────────────────────────
def enhance_image(image_bytes):
    """
    Aumenta brillo y contraste para ayudar a la IA en fotos oscuras.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # 1. Aumentar Brillo (1.2 = 20% más brillante)
        enhancer_bright = ImageEnhance.Brightness(img)
        img = enhancer_bright.enhance(1.2)
        
        # 2. Aumentar Contraste (1.3 = 30% más contraste)
        enhancer_contrast = ImageEnhance.Contrast(img)
        img = enhancer_contrast.enhance(1.3)
        
        # Guardar en buffer
        output_buffer = io.BytesIO()
        # Mantenemos formato original o convertimos a JPEG si es complejo
        fmt = img.format if img.format else 'JPEG'
        img.save(output_buffer, format=fmt)
        return output_buffer.getvalue(), fmt
    except Exception as e:
        logger.error(f"Error mejorando imagen: {e}")
        return image_bytes, 'JPEG' # Devolver original si falla

# ── Endpoints ───────────────────────────────────────────────────────────────
# ── Models ────────────────────────────────────────────────────────────────────
from pydantic import BaseModel

class ImageInput(BaseModel):
    image: str

# ── Endpoints ───────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "ok", "message": "API Activa y Mejorada (JSON Support). Use POST /api/analyze"}

@app.post("/api/analyze")
async def analyze_image(
    data: ImageInput,
):
    """
    1. Recibe URL de imagen en JSON.
    2. Descarga la imagen.
    3. Mejor iluminación (Pre-procesamiento).
    4. Envía a n8n.
    """
    
    # Validar webhook
    if not N8N_WEBHOOK_URL:
        raise HTTPException(503, "Webhook no configurado en .env (N8N_WEBHOOK_URL)")

    image_url = data.image
    logger.info(f"Procesando URL: {image_url}")

    # Descargar imagen
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp_img = await client.get(image_url)
            resp_img.raise_for_status()
            content = resp_img.content
            content_type = resp_img.headers.get("content-type", "image/jpeg")
    except Exception as e:
        logger.error(f"Error descargando imagen: {e}")
        raise HTTPException(400, f"No se pudo descargar la imagen: {str(e)}")

    # MEJORAR IMAGEN (Soluciona problema de iluminación)
    enhanced_content, fmt = enhance_image(content)
    logger.info(f"Imagen procesada ({len(content)} -> {len(enhanced_content)} bytes)")
    
    # Preparar para n8n
    # Usamos un nombre genérico o derivado de la URL si es posible, pero simple
    filename = f"downloaded_image.{fmt.lower()}"
    mime = f"image/{fmt.lower()}"
    
    # n8n espera el archivo en un campo multipart. Usaremos 'data'.
    files = {'data': (filename, enhanced_content, mime)}
    
    logger.info(f"Enviando imagen mejorada a n8n: {N8N_WEBHOOK_URL}")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # POST directo con files
            response = await client.post(N8N_WEBHOOK_URL, files=files) 
            response.raise_for_status()
            
    except httpx.TimeoutException:
        logger.error("Timeout esperando a n8n")
        raise HTTPException(504, "n8n tardó demasiado (60s).")
        
    except Exception as e:
        logger.error(f"Error n8n: {e}")
        detail = str(e)
        if isinstance(e, httpx.HTTPStatusError):
            detail = e.response.text
        raise HTTPException(502, f"Error conectando con n8n: {detail}")

    # Retornar JSON
    try:
        return response.json()
    except:
        return {"raw_response": response.text}

# ── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
