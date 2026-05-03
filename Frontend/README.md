# App DeepLLike 
# Alejandro Arana Fernandez - 2220232039


# Agentes usados

# 1. Detector: langdetect 
# 2. Traductor: Ollama qwen2.5:7b
# 3. Revisor: Ollama qwen2.5:7b

## Requisitos
- Python 3.10+
- Node.js 18+
- Ollama instalado (https://ollama.com/download)
- Modelo: `ollama pull qwen2.5:7b`
- Mínimo 8GB RAM

## Instalación
### Backend
cd backend
pip install -r requirements.txt

### Frontend
cd Frontend
npm install

## Ejecución
### Terminal 1
cd .\backend\ 
uvicorn main:app --reload --port 8000

### Terminal 2
cd .\Frontend\
npm run dev

## Uso
Abrir http://localhost:5173 en el navegador.
Para correr la app multiagente
