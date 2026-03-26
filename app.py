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
import anthropic
import traceback
import json
import re

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
API_PORT = int(os.getenv("PORT", "8001"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_fibra_optica")

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="API Fibra Óptica v3.0",
    description="Recibe URL de imagen y la analiza con Claude.",
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
ANALYSIS_PROMPT = """Eres un experto en redes de fibra óptica analizando una imagen de un nodo ATP (caja de distribución de fibra).

CONTEXTO CRÍTICO - cómo se ven los puertos:
Los nodos ATP tienen dos tipos de elementos verdes que PARECEN similares pero son muy distintos:

1. TAPA PROTECTORA (puerto DISPONIBLE):
   - Pieza de plástico verde SÓLIDA, cuadrada o rectangular
   - NO tiene ningún cable saliendo
   - Es completamente plana/maciza por delante
   - Se encaja dentro del adaptador como un capuchón ciego

2. CONECTOR SC/APC ACTIVO (puerto OCUPADO):
   - Tiene un cable de fibra óptica (pigtail) que ENTRA por la parte trasera/lateral
   - El cable es delgado (1-2mm) con revestimiento de colores (amarillo, azul, naranja, blanco, etc.)
   - Se puede ver el cable ANTES de entrar al conector
   - La diferencia visual: tiene un cable conectado a él

FASE 1 - INVENTARIO:
Describe brevemente la caja, total de puertos visibles y etiqueta/código.

FASE 2 - ANÁLISIS PUERTO POR PUERTO:
Para cada puerto de izquierda a derecha, escribe:
Puerto X: [¿Ves algún cable conectado a él? Describe color y forma de lo que ves] → OCUPADO / DISPONIBLE

IMPORTANTE: La mayoría de puertos en campo tienen TAPAS PROTECTORAS. Solo clasifica como OCUPADO si claramente ves un cable de fibra conectado. En caso de duda → DISPONIBLE.

FASE 3 - JSON:
Basándote SOLO en los puertos donde viste cable conectado, devuelve:
<json>
{
  "total_ports": <total de puertos en la caja>,
  "available_ports": [<puertos SIN cable: tapas protectoras o vacíos>],
  "occupied_ports": [<puertos CON cable de fibra visible conectado>],
  "technical_reference": "<código de etiqueta del nodo, o null>",
  "observations": "<descripción de lo que viste en cada puerto que clasificaste como ocupado>"
}
</json>"""

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
    if not ANTHROPIC_API_KEY:
        raise HTTPException(503, "ANTHROPIC_API_KEY no configurado.")

    image_url = data.image
    logger.info(f"Analizando imagen: {image_url}")

    # Descargar imagen
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            img_response = await client.get(image_url)
            img_response.raise_for_status()
            image_bytes = img_response.content
            content_type = img_response.headers.get("content-type", "image/jpeg").split(";")[0]
            # Claude solo acepta estos tipos
            if content_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                content_type = "image/jpeg"
    except httpx.TimeoutException:
        raise HTTPException(504, "Timeout descargando la imagen.")
    except Exception as e:
        raise HTTPException(400, f"No se pudo descargar la imagen: {str(e)}")

    # Llamar a Claude
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": content_type,
                                "data": base64.b64encode(image_bytes).decode("utf-8"),
                            },
                        },
                        {
                            "type": "text",
                            "text": ANALYSIS_PROMPT
                        }
                    ],
                }
            ],
        )
        raw_text = message.content[0].text.strip()
        logger.info(f"Respuesta Claude: {raw_text}")
    except Exception as e:
        raise HTTPException(502, f"Error en Claude: {str(e)}")

    # Parsear JSON
    try:
        # Buscar JSON dentro de <json>...</json>
        json_match = re.search(r'<json>\s*(.*?)\s*</json>', raw_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(1))
        else:
            # Fallback: limpiar markdown y parsear directamente
            cleaned = raw_text
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            result = json.loads(cleaned.strip())
        return result
    except json.JSONDecodeError:
        return {"raw_response": raw_text}

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
