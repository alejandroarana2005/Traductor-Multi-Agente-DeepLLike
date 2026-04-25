// src/App.jsx
import { useState, useRef } from "react"

const API = "http://localhost:8000"

const AGENT_CONFIG = {
  detector:  { label: "Detector",  desc: "Identifica el idioma" },
  traductor: { label: "Traductor", desc: "Qwen vía Ollama" },
  revisor:   { label: "Revisor",   desc: "Verifica calidad" },
}

function AgentCard({ name, status, result }) {
  const cfg = AGENT_CONFIG[name]
  const styles = {
    idle:    "bg-white/[0.07] border-white/[0.07] text-gray-500",
    running: "bg-orange-400/10 border-orange-400/25 text-orange-300",
    done:    "bg-emerald-400/10 border-emerald-400/25 text-emerald-300",
    skip:    "bg-amber-400/10 border-amber-400/25 text-amber-300",
  }

  return (
    <div className={`backdrop-blur-sm border rounded-xl p-4 transition-all duration-300 ${styles[status]}`}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-semibold text-sm tracking-wide">{cfg.label}</span>
        {status === "running" && (
          <span className="text-xs animate-pulse opacity-70">procesando...</span>
        )}
        {status === "done" && (
          <span className="text-xs opacity-60">listo</span>
        )}
      </div>
      <p className="text-xs opacity-50 leading-relaxed">{result || cfg.desc}</p>
    </div>
  )
}

export default function App() {
  const [languages, setLanguages]       = useState({})
  const [targetLang, setTargetLang]     = useState("en")
  const [inputText, setInputText]       = useState("")
  const [translation, setTranslation]   = useState("")
  const [detectedLang, setDetectedLang] = useState("")
  const [isLoading, setIsLoading]       = useState(false)
  const [agentStates, setAgentStates]   = useState({
    detector:  { status: "idle", result: "" },
    traductor: { status: "idle", result: "" },
    revisor:   { status: "idle", result: "" },
  })

  const loaded = useRef(false)
  // eslint-disable-next-line react-hooks/refs
  if (!loaded.current) {
    loaded.current = true
    fetch(`${API}/languages`)
      .then(r => r.json())
      .then(setLanguages)
      .catch(() => console.error("Backend no disponible"))
  }

  function resetAgents() {
    setAgentStates({
      detector:  { status: "idle", result: "" },
      traductor: { status: "idle", result: "" },
      revisor:   { status: "idle", result: "" },
    })
    setTranslation("")
    setDetectedLang("")
  }

  function updateAgent(name, status, result = "") {
    setAgentStates(prev => ({ ...prev, [name]: { status, result } }))
  }

  async function handleTranslate() {
    if (!inputText.trim() || isLoading) return

    resetAgents()
    setIsLoading(true)

    try {
      const res = await fetch(`${API}/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: inputText, target_lang: targetLang }),
      })

      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer    = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n\n")
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue

          const payload = line.slice(6).trim()
          if (payload === "[DONE]") { setIsLoading(false); continue }

          const data = JSON.parse(payload)

          switch (data.type) {
            case "agent_start":
              updateAgent(data.agent, "running")
              break
            case "agent_done":
              updateAgent(data.agent, "done", data.result)
              if (data.agent === "detector") setDetectedLang(data.metadata?.display || "")
              break
            case "agent_skip":
              updateAgent(data.agent, "skip", data.message)
              break
            case "final":
              setTranslation(data.translation)
              break
          }
        }
      }
    // eslint-disable-next-line no-unused-vars
    } catch (err) {
      setTranslation("Error conectando con el backend. ¿Está corriendo uvicorn?")
    } finally {
      setIsLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && e.ctrlKey) handleTranslate()
  }

  return (
    <div className="min-h-screen flex flex-col items-center px-4 py-12">

      {/* Header */}
      <div className="mb-10 text-center">
        <h1 className="font-display font-semibold leading-tight">
          <span className="block text-6xl text-white tracking-wide">Traductor</span>
          <span className="block text-6xl tracking-wide">
            <span className="text-blue-400 italic">Multi</span>
            <span className="text-gray-300"> Agente</span>
          </span>
        </h1>
        <p className="text-sm text-gray-500 mt-2 font-light tracking-wide">
          Detector - Traductor - Revisor : Qwen2.5 vía Ollama local
        </p>
      </div>

      {/* Paneles principales */}
      <div className="w-full max-w-4xl grid grid-cols-2 gap-4 mb-4">

        {/* Panel izquierdo — entrada */}
        <div className="bg-white/[0.05] backdrop-blur-sm rounded-2xl border border-white/[0.06] p-5 flex flex-col">
          <div className="h-9 flex items-center justify-between mb-4">
            <span className="text-xs font-semibold text-blue-400 uppercase tracking-widest">
              Texto origen
            </span>
            {detectedLang && (
              <span className="text-xs bg-blue-500/10 text-blue-300 border border-blue-500/20 px-2.5 py-0.5 rounded-full">
                {detectedLang}
              </span>
            )}
          </div>
          <textarea
            className="flex-1 resize-none outline-none bg-transparent text-white text-base p-0
                      leading-relaxed placeholder:text-gray-500 min-h-[220px] font-light"
            placeholder="Escribe o pega el texto aquí... (Ctrl+Enter para traducir)"
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
          />
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-white/[0.07]">
            <span className="text-xs text-gray-100 font-light tabular-nums">
              {inputText.length} / 2000
            </span>
            <button
              onClick={handleTranslate}
              disabled={isLoading || !inputText.trim()}
              className="px-6 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg
                         hover:bg-blue-500 active:bg-blue-700
                         disabled:opacity-25 disabled:cursor-not-allowed
                         transition-colors tracking-wide"
            >
              {isLoading ? "Traduciendo..." : "Traducir"}
            </button>
          </div>
        </div>

        {/* Panel derecho — resultado */}
        <div className="bg-white/[0.05] backdrop-blur-sm rounded-2xl border border-white/[0.06] p-5 flex flex-col">
          <div className="h-9 flex items-center justify-between mb-4">
            <span className="text-xs font-semibold text-blue-400 uppercase tracking-widest">
              Traducción
            </span>
            <select
              value={targetLang}
              onChange={e => setTargetLang(e.target.value)}
              className="text-xs bg-[#111827] border border-white/[0.12] rounded-lg px-3 py-1.5
                         outline-none text-gray-300 cursor-pointer
                         hover:border-white/25 transition-colors"
            >
              {Object.entries(languages).map(([code, name]) => (
                <option key={code} value={code}>{name}</option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-h-[220px] text-white text-base leading-relaxed whitespace-pre-wrap font-light">
            {isLoading ? (
              <div className="space-y-3 pt-1">
                <div className="skeleton-line h-3.5 w-full" />
                <div className="skeleton-line h-3.5 w-5/6" />
                <div className="skeleton-line h-3.5 w-full" />
                <div className="skeleton-line h-3.5 w-4/6" />
                <div className="skeleton-line h-3.5 w-full" />
                <div className="skeleton-line h-3.5 w-3/6" />
              </div>
            ) : translation ? (
              translation
            ) : (
              <span className="text-gray-500">La traducción aparecerá aquí...</span>
            )}
          </div>
          <div className="mt-4 pt-4 border-t border-white/[0.07] flex justify-end">
            {translation && (
              <button
                onClick={() => navigator.clipboard.writeText(translation)}
                className="flex items-center gap-1.5 text-xs text-gray-100 hover:text-blue-400 transition-colors tracking-wide"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
                  <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
                </svg>
                Copiar traducción
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Panel de agentes */}
      <div className="w-full max-w-4xl bg-white/[0.05] backdrop-blur-sm rounded-2xl border border-white/[0.06] p-5">
        <p className="text-xs font-semibold text-blue-400 uppercase tracking-widest mb-4">
          Pipeline de agentes
        </p>
        <div className="grid grid-cols-3 gap-3">
          {Object.keys(AGENT_CONFIG).map(name => (
            <AgentCard
              key={name}
              name={name}
              status={agentStates[name].status}
              result={agentStates[name].result}
            />
          ))}
        </div>
      </div>

      {/* Footer */}
      <footer className="w-full max-w-4xl mt-6 pt-4 border-t border-white/[0.07] flex items-center justify-between">
        <span className="text-sm text-gray-400 font-light">
          Alejandro Arana Fernandez
          <span className="mx-2 text-white/20">·</span>
          <span className="text-gray-600 text-xs tabular-nums">2220232039</span>
        </span>
        <a
          href="mailto:alejandro.arana@estudiantesunibague.edu.co"
          className="text-xs text-gray-600 hover:text-blue-400 transition-colors tracking-wide"
        >
          alejandro.arana@estudiantesunibague.edu.co
        </a>
      </footer>

    </div>
  )
}
