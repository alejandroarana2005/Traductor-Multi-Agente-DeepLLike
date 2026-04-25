# orchestrator.py
from agents import DetectorAgent, TranslatorAgent, ReviewerAgent
from typing import AsyncGenerator
import json
import asyncio

# Tabla de idiomas para el orquestador
LANG_NAMES = {
    "es": "Spanish",  "en": "English",   "fr": "French",
    "de": "German",   "pt": "Portuguese", "it": "Italian",
    "zh-cn": "Chinese", "ja": "Japanese", "ko": "Korean",
    "ru": "Russian",  "ar": "Arabic",
}


class TranslationOrchestrator:
    """
    El orquestador es el cerebro del sistema multi-agente.
    Su única responsabilidad es COORDINAR: sabe qué agente
    llamar, en qué orden, y qué hacer con cada resultado.

    Los agentes no se conocen entre sí — solo el orquestador
    sabe que existen. Esto se llama "acoplamiento débil" y es
    lo que hace al sistema fácil de extender.
    """

    def __init__(self, model: str = "qwen2.5:7b"):
        # Instancia los tres agentes una sola vez
        self.detector   = DetectorAgent()
        self.translator = TranslatorAgent(model)
        self.reviewer   = ReviewerAgent(model)

    async def run(
        self,
        text: str,
        target_lang_code: str
    ) -> AsyncGenerator[str, None]:
        """
        Genera eventos SSE en tiempo real mientras los agentes trabajan.

        ¿Por qué SSE y no esperar al resultado final?
        Porque los LLMs son lentos (2-10 segundos por llamada).
        Con SSE el frontend muestra progreso inmediato, igual que DeepL.
        El usuario sabe que algo está pasando, no ve una pantalla congelada.
        """

        target_lang = LANG_NAMES.get(target_lang_code, target_lang_code)

        # Función helper: convierte un dict a evento SSE con formato correcto
        def event(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        # ── Señal de inicio ────────────────────────────────────────────────
        yield event({
            "type": "orchestrator",
            "message": "Pipeline multi-agente iniciado..."
        })

        # ══════════════════════════════════════════════════════════════════
        # PASO 1 — Agente Detector
        # El orquestador delega, recibe el resultado, y lo emite al frontend
        # ══════════════════════════════════════════════════════════════════
        yield event({
            "type": "agent_start",
            "agent": "detector",
            "icon": "🔍",
            "message": "Detectando idioma del texto..."
        })

        # run_in_executor: los agentes son síncronos (LangChain blocking),
        # pero FastAPI es async. Esto los ejecuta en un thread separado
        # sin bloquear el event loop principal.
        loop = asyncio.get_event_loop()
        det = await loop.run_in_executor(
            None, lambda: self.detector.run(text)
        )

        source_lang = det.output  # ej: "Spanish"

        yield event({
            "type": "agent_done",
            "agent": "detector",
            "icon": "🔍",
            "result": f"Idioma detectado: {det.metadata['display']}",
            "metadata": det.metadata
        })

        # ── Caso especial: origen == destino ──────────────────────────────
        # No tiene sentido llamar al LLM para "traducir" español a español.
        # El orquestador toma esta decisión antes de gastar recursos.
        if det.metadata["code"] == target_lang_code:
            yield event({
                "type": "agent_skip",
                "agent": "traductor",
                "message": "Idioma origen igual al destino, no se necesita traducción"
            })
            yield event({"type": "final", "translation": text})
            yield "data: [DONE]\n\n"
            return

        # ══════════════════════════════════════════════════════════════════
        # PASO 2 — Agente Traductor
        # ══════════════════════════════════════════════════════════════════
        yield event({
            "type": "agent_start",
            "agent": "traductor",
            "icon": "🌐",
            "message": f"Traduciendo {source_lang} → {target_lang}..."
        })

        trans = await loop.run_in_executor(
            None,
            lambda: self.translator.run(text, source_lang, target_lang)
        )

        yield event({
            "type": "agent_done",
            "agent": "traductor",
            "icon": "🌐",
            # Mostramos solo los primeros 200 chars para no saturar el evento
            "result": trans.output[:200] + ("..." if len(trans.output) > 200 else ""),
            "metadata": trans.metadata
        })

        # ══════════════════════════════════════════════════════════════════
        # PASO 3 — Agente Revisor
        # Recibe tanto el original como la traducción para poder comparar
        # ══════════════════════════════════════════════════════════════════
        yield event({
            "type": "agent_start",
            "agent": "revisor",
            "icon": "✅",
            "message": "Revisando calidad y fidelidad..."
        })

        rev = await loop.run_in_executor(
            None,
            lambda: self.reviewer.run(
                text, trans.output, source_lang, target_lang
            )
        )

        yield event({
            "type": "agent_done",
            "agent": "revisor",
            "icon": "✅",
            "result": f"Revisión completada — ratio: {rev.metadata.get('length_ratio', '?')}",
            "metadata": rev.metadata
        })

        # ── Resultado final ────────────────────────────────────────────────
        # El output del Revisor es la traducción definitiva.
        # Si el revisor no cambió nada, devuelve la misma traducción.
        yield event({
            "type": "final",
            "translation": rev.output,
            "source_lang": source_lang,
        })

        # [DONE] es la señal que el frontend espera para saber que terminó
        yield "data: [DONE]\n\n"