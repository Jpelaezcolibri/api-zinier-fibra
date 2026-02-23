import os
import logging
import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import traceback

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv()

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
API_PORT = int(os.getenv("PORT", "8001"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_imagen_n8n")

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="API Fibra Óptica v3.0",
    description="Recibe URL de imagen y la analiza con Gemini via n8n.",
    version="3.0.0",
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = "".join(traceback.format_exception(None, exc, exc.__traceback__))
    logger.error(f"CRITICAL ERROR: {error_msg}")
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "trace": error_msg})

# ── Middleware CORS ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ────────────────────────────────────────────────────────────────────
class ImageInput(BaseModel):
    image: str

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "API Fibra Óptica v3.0 activa.",
        "uso": "POST /api/analyze con body: {\"image\": \"https://url-de-la-imagen.jpg\"}"
    }

@app.post("/api/analyze")
async def analyze_image(data: ImageInput):
    """
    Recibe: {"image": "https://cualquier-url-publica/imagen.jpg"}
    Devuelve: JSON con análisis de puertos de fibra óptica.
    """
    if not N8N_WEBHOOK_URL:
        raise HTTPException(503, "N8N_WEBHOOK_URL no configurado en .env")

    image_url = data.image
    logger.info(f"Analizando imagen: {image_url}")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                N8N_WEBHOOK_URL,
                json={"image": image_url}
            )
            response.raise_for_status()

    except httpx.TimeoutException:
        raise HTTPException(504, "n8n tardó demasiado (timeout 60s).")
    except Exception as e:
        detail = e.response.text if isinstance(e, httpx.HTTPStatusError) else str(e)
        raise HTTPException(502, f"Error en n8n: {detail}")

    try:
        return response.json()
    except Exception:
        return {"raw_response": response.text}

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
