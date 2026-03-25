import os
import logging
import base64
import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import google.generativeai as genai
import traceback
import json

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
API_PORT = int(os.getenv("PORT", "8001"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_fibra_optica")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="API Fibra Óptica v3.0",
    description="Recibe URL de imagen y la analiza con Gemini directamente.",
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

# ── Prompt ────────────────────────────────────────────────────────────────────
ANALYSIS_PROMPT = """Eres un experto en redes de fibra óptica. Analiza esta imagen de un nodo ATP y detecta el estado de los puertos.

Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta (sin markdown, sin explicaciones):
{
  "total_ports": <número total de puertos visibles>,
  "available_ports": [<lista de números de puertos libres/disponibles>],
  "occupied_ports": [<lista de números de puertos ocupados/conectados>],
  "technical_reference": "<referencia técnica o etiqueta del equipo si es visible, sino null>",
  "observations": "<observaciones relevantes sobre el estado del nodo>"
}

Si no puedes determinar un valor con certeza, usa null para strings y [] para listas."""

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
    if not GEMINI_API_KEY:
        raise HTTPException(503, "GEMINI_API_KEY no configurado.")

    image_url = data.image
    logger.info(f"Analizando imagen: {image_url}")

    # Descargar imagen
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            img_response = await client.get(image_url)
            img_response.raise_for_status()
            image_bytes = img_response.content
            content_type = img_response.headers.get("content-type", "image/jpeg").split(";")[0]
    except httpx.TimeoutException:
        raise HTTPException(504, "Timeout descargando la imagen.")
    except Exception as e:
        raise HTTPException(400, f"No se pudo descargar la imagen: {str(e)}")

    # Llamar a Gemini
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        image_part = {
            "inline_data": {
                "mime_type": content_type,
                "data": base64.b64encode(image_bytes).decode("utf-8")
            }
        }
        response = model.generate_content([ANALYSIS_PROMPT, image_part])
        raw_text = response.text.strip()
        logger.info(f"Respuesta Gemini: {raw_text}")
    except Exception as e:
        raise HTTPException(502, f"Error en Gemini: {str(e)}")

    # Parsear JSON
    try:
        # Limpiar posible markdown
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        result = json.loads(raw_text.strip())
        return result
    except json.JSONDecodeError:
        return {"raw_response": raw_text}

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
