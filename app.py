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
ANALYSIS_PROMPT = """Analiza esta imagen de un nodo ATP de fibra óptica y determina el estado de cada puerto.

CÓMO IDENTIFICAR CADA PUERTO:
- OCUPADO: tiene un cable de fibra óptica (delgado, coloreado) entrando por detrás del conector verde. El conector puede sobresalir ligeramente y tiene una fibra conectada.
- DISPONIBLE: tiene solo una tapa de plástico verde sin cable alguno.

Examina cuidadosamente cada puerto individualmente. Numera de izquierda a derecha desde el 1.

Responde ÚNICAMENTE con este JSON exacto:
<resultado>
{"total_ports": X, "available_ports": [lista], "occupied_ports": [lista]}
</resultado>"""

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
            max_tokens=8000,
            thinking={
                "type": "enabled",
                "budget_tokens": 4000
            },
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
        # Extraer bloque de texto (ignorar bloque de thinking)
        raw_text = ""
        for block in message.content:
            if block.type == "text":
                raw_text = block.text.strip()
                break
        logger.info(f"Respuesta Claude: {raw_text}")
    except Exception as e:
        raise HTTPException(502, f"Error en Claude: {str(e)}")

    # Parsear JSON
    try:
        # 1. Buscar dentro de <resultado>...</resultado>
        match = re.search(r'<resultado>\s*(.*?)\s*</resultado>', raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(1).strip())

        # 2. Buscar bloque ```json ... ``` en cualquier parte del texto
        match = re.search(r'```json\s*(.*?)\s*```', raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(1).strip())

        # 3. Buscar primer { ... } válido
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(0).strip())

        return {"raw_response": raw_text}
    except json.JSONDecodeError:
        return {"raw_response": raw_text}

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
