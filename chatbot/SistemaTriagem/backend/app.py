from flask import Flask, request, jsonify
from dotenv import load_dotenv
load_dotenv()
import os
import sqlite3
import google.generativeai as genai
from datetime import datetime
from flask_cors import CORS

# =============================
# CONFIG GEMINI
# =============================
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("API key not found. Please set the GOOGLE_API_KEY environment variable.")

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

system_prompt = (
    "You are an AI Health Assistant. "
    "Your role is to gather basic information (Name, Age, Zip Code, Phone Number, and Symptoms) "
    "from the user. "
    "However, DO NOT ask for name, age, address, phone number, or symptoms yourself just comment on them. "
    "The comments should keep the conversation going and make the user feel comfortable. "
    "After the user has provided all necessary information, provide a summary of the information collected, "
    "and send this link to the person to talk to a real doctor: https://meet.google.com/ovr-ocwa-mxi."
)

# Inicializa o chat com histórico inicial
chat = model.start_chat(history=[{"role": "user", "parts": [system_prompt]}])

# =============================
# BANCO SQLITE
# =============================
DB_PATH = os.path.join(os.path.dirname(__file__), "conversas.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dialogos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            autor TEXT,
            mensagem TEXT
        )
    """)
    conn.commit()
    conn.close()

def salvar_dialogo(autor, mensagem):
    # Converte objetos em string, se necessário
    if not isinstance(mensagem, str):
        mensagem = str(mensagem)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO dialogos (timestamp, autor, mensagem) VALUES (?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), autor, mensagem)
    )
    conn.commit()
    conn.close()

def salvar_paciente(dados):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO pacientes (nome, idade, endereco, telefone, sintomas, data_registro) VALUES (?, ?, ?, ?, ?, ?)",
        (dados.get("nome"), dados.get("idade"), dados.get("endereco"),
         dados.get("telefone"), dados.get("sintomas"),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()
    print("✅ Dados do paciente salvos no banco!")

init_db()    

# =============================
# FLASK APP
# =============================
app = Flask(__name__)
CORS(app)  # permite frontend acessar backend

@app.route("/chat", methods=["POST"])
def chat_api():
    data = request.json
    user_message = data.get("message", "")

    if not user_message:
        return jsonify({"error": "Mensagem vazia"}), 400

    # Salva mensagem do usuário
    salvar_dialogo("Usuário", user_message)

    # Obtém resposta do Gemini AI
    response = chat.send_message(user_message)

    # Extrai texto da resposta
    if isinstance(response, str):
        ai_message = response
    else:
        ai_message = getattr(response, "text", str(response))

    # Salva resposta do assistente
    salvar_dialogo("Assistente", ai_message)

    return jsonify({"reply": ai_message})

@app.route("/history", methods=["GET"])
def get_history():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, autor, mensagem FROM dialogos ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    # Retorna como lista de objetos JSON
    history = [{"timestamp": ts, "autor": autor, "mensagem": msg} for ts, autor, msg in rows]
    return jsonify(history)

if __name__ == "__main__":
    init_db()
    app.run(port=5000, debug=True)