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
ANALYSIS_PROMPT = """Eres un experto en redes de fibra óptica. Analiza esta imagen de un nodo ATP (caja de distribución de fibra óptica) y detecta con precisión el estado de cada puerto.

CRITERIOS IMPORTANTES para identificar el estado de los puertos:
- Puerto OCUPADO: tiene un conector SC/APC insertado (generalmente verde brillante, con cable de fibra saliendo). El conector tiene forma cilíndrica con un cable conectado.
- Puerto DISPONIBLE: está vacío (sin nada) o tiene solo una tapa protectora pequeña (cap de plástico sin cable). Las tapas protectoras NO tienen cable saliendo.
- Cuenta los puertos de izquierda a derecha, comenzando desde el 1.
- Si ves números impresos en la caja, úsalos para identificar cada puerto.
- Sé conservador: si no puedes determinar con certeza el estado de un puerto, indícalo en observaciones.

Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta (sin markdown, sin explicaciones):
{
  "total_ports": <número total de puertos visibles en la caja>,
  "available_ports": [<lista de números de puertos vacíos o con tapa sin cable>],
  "occupied_ports": [<lista de números de puertos con conector SC/APC y cable activo>],
  "technical_reference": "<código o etiqueta del nodo visible en la caja, sino null>",
  "observations": "<descripción del estado general, colores observados, dudas sobre puertos específicos>"
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
            max_tokens=1024,
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
