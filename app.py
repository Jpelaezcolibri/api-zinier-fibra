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

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
API_PORT = int(os.getenv("PORT", "8001"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_fibra_optica")

# ── Supabase ──────────────────────────────────────────────────────────────────
supabase_client = None
if SUPABASE_URL and SUPABASE_KEY:
    from supabase import create_client
    supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Supabase conectado.")
else:
    logger.warning("Supabase no configurado. El aprendizaje estará desactivado.")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="API Fibra Óptica v4.0",
    description="Analiza imágenes de nodos ATP con aprendizaje continuo via Supabase.",
    version="4.0.0",
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = "".join(traceback.format_exception(None, exc, exc.__traceback__))
    logger.error(f"CRITICAL ERROR: {error_msg}")
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "trace": error_msg})

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

def format_result(data: dict, source: str = None) -> dict:
    """Agrega conteos al resultado y ordena los campos."""
    occupied = data.get("occupied_ports", [])
    available = data.get("available_ports", [])
    result = {
        "total_ports": data.get("total_ports", 0),
        "occupied_count": len(occupied),
        "occupied_ports": sorted(occupied),
        "available_count": len(available),
        "available_ports": sorted(available),
    }
    if source:
        result["_source"] = source
    return result

class FeedbackInput(BaseModel):
    image_url: str
    correct_result: dict
    notes: str = None

# ── Supabase helpers ──────────────────────────────────────────────────────────
def check_known_image(image_url: str):
    """Si esta imagen ya fue corregida, devuelve el resultado guardado."""
    if not supabase_client:
        return None
    try:
        result = supabase_client.table("port_corrections") \
            .select("correct_result") \
            .eq("image_url", image_url) \
            .order("created_at", desc=True) \
            .limit(1).execute()
        if result.data:
            return result.data[0]["correct_result"]
    except Exception as e:
        logger.warning(f"Error verificando imagen conocida: {e}")
    return None

def get_recent_corrections(limit: int = 5):
    """Obtiene las últimas correcciones para usarlas como ejemplos en el prompt."""
    if not supabase_client:
        return []
    try:
        result = supabase_client.table("port_corrections") \
            .select("image_url, correct_result, notes") \
            .order("created_at", desc=True) \
            .limit(limit).execute()
        return result.data or []
    except Exception as e:
        logger.warning(f"Error obteniendo correcciones: {e}")
        return []

# ── Prompt builder ────────────────────────────────────────────────────────────
BASE_PROMPT = """Eres un experto en redes de fibra óptica. Analiza esta imagen de un nodo ATP.

CÓMO IDENTIFICAR EL ESTADO DE CADA PUERTO:
- OCUPADO: tiene un conector SC/APC insertado (cilíndrico, verde) con una fibra óptica (cable delgado) saliendo por la parte trasera. Busca el cable que sale del adaptador.
- DISPONIBLE: tiene solo una tapa protectora plana de plástico. Sin cable. Solo plástico sólido tapando el puerto.

REGLA CLAVE: si ves un cable de fibra conectado al puerto → OCUPADO. Si solo hay tapa plástica sin cable → DISPONIBLE.

Numera los puertos de izquierda a derecha empezando en 1.
{ejemplos}
Responde ÚNICAMENTE con este JSON (sin texto adicional, sin markdown):
{{"total_ports": X, "available_ports": [lista], "occupied_ports": [lista]}}"""

def build_prompt() -> str:
    corrections = get_recent_corrections()
    if not corrections:
        return BASE_PROMPT.replace("{ejemplos}", "")

    lines = "\nCORRECCIONES PREVIAS (casos reales ya resueltos - aprende de ellos):\n"
    for c in corrections:
        cr = json.dumps(c["correct_result"])
        note = f" | Nota: {c['notes']}" if c.get("notes") else ""
        lines += f"- Resultado correcto: {cr}{note}\n"
    lines += "\n"
    return BASE_PROMPT.replace("{ejemplos}", lines)

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "status": "ok",
        "version": "4.0.0",
        "aprendizaje": "activo" if supabase_client else "inactivo (configura SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY)",
        "endpoints": {
            "analizar imagen": "POST /api/analyze  →  {\"image\": \"https://url-imagen.jpg\"}",
            "corregir resultado": "POST /api/feedback  →  {\"image_url\": \"...\", \"correct_result\": {...}, \"notes\": \"...\"}",
            "ver correcciones": "GET /api/corrections"
        }
    }

@app.post("/api/analyze")
async def analyze_image(data: ImageInput):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(503, "ANTHROPIC_API_KEY no configurado.")

    image_url = data.image
    logger.info(f"Analizando: {image_url}")

    # 1. Imagen conocida → devolver resultado guardado directamente
    known = check_known_image(image_url)
    if known:
        logger.info(f"Imagen ya corregida, devolviendo memoria: {known}")
        return format_result(known, source="memory")

    # 2. Descargar imagen
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            img_resp = await client.get(image_url)
            img_resp.raise_for_status()
            image_bytes = img_resp.content
            content_type = img_resp.headers.get("content-type", "image/jpeg").split(";")[0]
            if content_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                content_type = "image/jpeg"
    except httpx.TimeoutException:
        raise HTTPException(504, "Timeout descargando la imagen.")
    except Exception as e:
        raise HTTPException(400, f"No se pudo descargar la imagen: {str(e)}")

    # 3. Llamar a Claude con prompt enriquecido con correcciones
    try:
        prompt = build_prompt()
        claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            messages=[{
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
                    {"type": "text", "text": prompt}
                ],
            }],
        )
        raw_text = message.content[0].text.strip()
        logger.info(f"Claude respondió: {raw_text}")
    except Exception as e:
        raise HTTPException(502, f"Error en Claude: {str(e)}")

    # 4. Parsear JSON
    try:
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            return format_result(json.loads(match.group(0).strip()), source="claude")
        return {"raw_response": raw_text}
    except json.JSONDecodeError:
        return {"raw_response": raw_text}


@app.post("/api/feedback")
async def submit_feedback(data: FeedbackInput):
    """
    Corrige el resultado de una imagen para que la API aprenda.
    Ejemplo:
    {
      "image_url": "https://i.postimg.cc/fRj9f6LG/...",
      "correct_result": {"total_ports": 8, "available_ports": [1,2,3,4,6,7,8], "occupied_ports": [5]},
      "notes": "El puerto 5 tenía cable activo, los demás solo tenían tapas protectoras verdes"
    }
    """
    if not supabase_client:
        raise HTTPException(503, "Supabase no configurado. Agrega SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en Render.")
    try:
        supabase_client.table("port_corrections").upsert({
            "image_url": data.image_url,
            "correct_result": data.correct_result,
            "notes": data.notes
        }, on_conflict="image_url").execute()
        return {"status": "ok", "message": "Corrección guardada. La API recordará esta imagen y usará el ejemplo para futuras imágenes similares."}
    except Exception as e:
        raise HTTPException(500, f"Error guardando corrección: {str(e)}")


@app.get("/api/corrections")
async def list_corrections():
    """Lista todas las correcciones guardadas."""
    if not supabase_client:
        raise HTTPException(503, "Supabase no configurado.")
    try:
        result = supabase_client.table("port_corrections") \
            .select("*").order("created_at", desc=True).execute()
        return {"total": len(result.data), "corrections": result.data}
    except Exception as e:
        raise HTTPException(500, f"Error: {str(e)}")


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
