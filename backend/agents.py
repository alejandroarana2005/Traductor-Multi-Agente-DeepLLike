# agents.py
from langchain_ollama import ChatOllama
from langchain.schema import HumanMessage, SystemMessage
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException
from dataclasses import dataclass

# Semilla fija: hace que langdetect sea determinista.
# Sin esto, el mismo texto puede dar idiomas distintos en cada llamada.
DetectorFactory.seed = 42

# ── Tablas de idiomas ──────────────────────────────────────────────────────────
# LANG_NAMES: los nombres en inglés que entiende el LLM en el prompt
# LANG_DISPLAY: los nombres visibles para el usuario en el frontend
LANG_NAMES = {
    "es": "Spanish", "en": "English", "fr": "French",
    "de": "German",  "pt": "Portuguese", "it": "Italian",
    "zh-cn": "Chinese", "ja": "Japanese", "ko": "Korean",
    "ru": "Russian", "ar": "Arabic",
}

LANG_DISPLAY = {
    "es": "Español",  "en": "English",  "fr": "Français",
    "de": "Deutsch",  "pt": "Português", "it": "Italiano",
    "zh-cn": "中文",  "ja": "日本語",   "ko": "한국어",
    "ru": "Русский",  "ar": "العربية",
}


# ── Contenedor de resultado ────────────────────────────────────────────────────
# Cada agente devuelve un AgentResult estandarizado.
# Así el orquestador puede leerlos todos de la misma forma,
# sin importar qué agente los produjo. (Principio de interfaz uniforme)
@dataclass
class AgentResult:
    agent: str        # nombre del agente que produjo el resultado
    output: str       # el texto principal del resultado
    metadata: dict = None  # datos extra (código ISO, dominio, etc.)


# ══════════════════════════════════════════════════════════════════════════════
# AGENTE 1 — Detector de idioma
# ──────────────────────────────
# Por qué NO usa el LLM: langdetect es un modelo estadístico de n-gramas.
# Es instantáneo (microsegundos) y 100% local. Usar el LLM para esto
# sería como usar una excavadora para clavar un clavo.
# ══════════════════════════════════════════════════════════════════════════════
class DetectorAgent:
    name = "detector"
    icon = "🔍"
    description = "Detecta el idioma del texto con langdetect"

    def run(self, text: str) -> AgentResult:
        try:
            code = detect(text)

            # langdetect devuelve "zh-cn" o "zh-tw" para chino.
            # Normalizamos ambos a "zh-cn" para simplificar.
            if code.startswith("zh"):
                code = "zh-cn"

            # Si el código no está en nuestra tabla, usamos inglés por defecto
            if code not in LANG_NAMES:
                code = "en"

            return AgentResult(
                agent=self.name,
                output=LANG_NAMES[code],   # ej: "Spanish"
                metadata={
                    "code": code,           # ej: "es"
                    "display": LANG_DISPLAY.get(code, code)  # ej: "Español"
                }
            )
        except LangDetectException:
            # Si el texto es demasiado corto o ambiguo, asumimos inglés
            return AgentResult(
                agent=self.name,
                output="English",
                metadata={"code": "en", "display": "English"}
            )


# ══════════════════════════════════════════════════════════════════════════════
# AGENTE 2 — Traductor
# ─────────────────────
# Por qué SÍ usa el LLM: la traducción requiere comprensión semántica
# profunda. Es la tarea principal del agente.
# Temperatura 0.1: queremos fidelidad al original, no creatividad.
# ══════════════════════════════════════════════════════════════════════════════
class TranslatorAgent:
    name = "traductor"
    icon = "🌐"
    description = "Traduce el texto usando Qwen vía Ollama"

    def __init__(self, model: str = "qwen2.5:7b"):
        # ChatOllama se conecta al servidor en localhost:11434
        self.llm = ChatOllama(model=model, temperature=0.1)

    def run(self, text: str, source_lang: str, target_lang: str) -> AgentResult:
        # El SystemMessage define el ROL del agente.
        # El HumanMessage es la tarea concreta.
        # Esta separación es la base del prompt engineering moderno.
        system = SystemMessage(content=f"""You are an expert professional translator.
Translate from {source_lang} to {target_lang}.

Rules:
- Return ONLY the translated text. No explanations, no notes, no quotes.
- Preserve all formatting and line breaks exactly.
- Maintain the original tone and register (formal/informal).
- Keep proper nouns and brand names unless a standard translation exists.""")

        human = HumanMessage(content=text)

        response = self.llm.invoke([system, human])

        return AgentResult(
            agent=self.name,
            output=response.content.strip(),
            metadata={"source": source_lang, "target": target_lang}
        )


# ══════════════════════════════════════════════════════════════════════════════
# AGENTE 3 — Revisor de calidad
# ──────────────────────────────
# Por qué es un agente separado: en sistemas multi-agente, la revisión
# la hace un LLM DISTINTO al que tradujo. Esto evita el sesgo de
# confirmación: el mismo modelo que cometió un error rara vez lo detecta.
# Temperatura 0.05: aún más conservador, queremos corrección, no variación.
# ══════════════════════════════════════════════════════════════════════════════
class ReviewerAgent:
    name = "revisor"
    icon = "✅"
    description = "Verifica calidad, tono y fidelidad de la traducción"

    def __init__(self, model: str = "qwen2.5:7b"):
        self.llm = ChatOllama(model=model, temperature=0.05)

    def run(
        self,
        original: str,
        translation: str,
        source_lang: str,
        target_lang: str
    ) -> AgentResult:

        # ── Verificación rápida sin LLM (heurística) ──────────────────────
        # Antes de gastar tiempo de inferencia, descartamos casos obvios
        ratio = len(translation) / max(len(original), 1)

        if translation.strip() == original.strip():
            return AgentResult(
                agent=self.name,
                output=translation,
                metadata={"status": "warning", "issue": "identical to original"}
            )

        if ratio < 0.15 or ratio > 6.0:
            # La traducción es sospechosamente corta o larga
            return AgentResult(
                agent=self.name,
                output=translation,
                metadata={"status": "warning", "issue": f"ratio inusual: {ratio:.2f}"}
            )

        # ── Revisión profunda con LLM ──────────────────────────────────────
        system = SystemMessage(content="""You are a professional translation quality reviewer.
Your job: review a translation and return an improved version ONLY if needed.
Return ONLY the final translation text — no comments, no explanations.""")

        human = HumanMessage(content=f"""Original ({source_lang}):
{original}

Translation ({target_lang}):
{translation}

Review for:
1. Accuracy — same meaning as original?
2. Fluency — sounds natural in {target_lang}?
3. Register — appropriate tone?

If the translation is good, return it as-is.
If it needs improvement, return the corrected version.""")

        response = self.llm.invoke([system, human])
        reviewed = response.content.strip()

        # Sanity check: si el revisor devuelve algo demasiado diferente,
        # preferimos la traducción original
        rev_ratio = len(reviewed) / max(len(translation), 1)
        if rev_ratio < 0.3 or rev_ratio > 3.0:
            reviewed = translation

        return AgentResult(
            agent=self.name,
            output=reviewed,
            metadata={"status": "ok", "length_ratio": round(ratio, 2)}
        )