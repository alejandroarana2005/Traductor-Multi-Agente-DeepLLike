# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from orchestrator import TranslationOrchestrator

# ── App FastAPI ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Traductor Multi-Agente",
    description="Pipeline: Detector → Traductor → Revisor",
    version="1.0.0"
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Sin esto, el navegador bloquea las peticiones del frontend (puerto 5173)
# al backend (puerto 8000). Es una restricción de seguridad del navegador,
# no de FastAPI. allow_origins=["*"] lo desactiva durante desarrollo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Idiomas soportados ─────────────────────────────────────────────────────────
LANGUAGES = {
    "es": "Español",   "en": "English",   "fr": "Français",
    "de": "Deutsch",   "pt": "Português",  "it": "Italiano",
    "zh-cn": "中文",   "ja": "日本語",    "ko": "한국어",
    "ru": "Русский",   "ar": "العربية",
}

# ── Modelo de la petición ──────────────────────────────────────────────────────
# Pydantic valida automáticamente que el JSON del frontend
# tenga exactamente estos campos y tipos. Si falta algo, FastAPI
# devuelve un error 422 con detalle — sin que tú escribas validación.
class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "en"


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT PRINCIPAL — POST /translate
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/translate")
async def translate(req: TranslateRequest):
    """
    Recibe texto + idioma destino.
    Devuelve un stream SSE con el progreso de los 3 agentes.

    ¿Por qué StreamingResponse?
    Porque el orquestador es un generador async que hace yield
    de eventos. StreamingResponse los empuja al cliente uno a uno,
    en tiempo real, sin esperar a que terminen todos los agentes.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="El texto no puede estar vacío")

    if req.target_lang not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Idioma no soportado: {req.target_lang}")

    orchestrator = TranslationOrchestrator(model="qwen2.5:7b")

    return StreamingResponse(
        orchestrator.run(req.text, req.target_lang),
        media_type="text/event-stream",
        headers={
            # Estos headers evitan que proxies o el navegador
            # acumulen los eventos en un buffer antes de enviarlos.
            # Sin ellos, el streaming se ve como una respuesta normal.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS DE SOPORTE
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/languages")
def get_languages():
    """El frontend lo llama al cargar para poblar los selectores de idioma."""
    return LANGUAGES


@app.get("/health")
async def health():
    """
    Verifica que Ollama esté corriendo antes de aceptar traducciones.
    El frontend puede llamar esto al iniciar para mostrar el estado.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            res = await client.get("http://localhost:11434/api/tags")
            models = [m["name"] for m in res.json().get("models", [])]
            return {
                "status": "ok",
                "type": "multi-agent",
                "agents": ["detector", "traductor", "revisor"],
                "ollama_models": models
            }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama no disponible: {e}"
        )