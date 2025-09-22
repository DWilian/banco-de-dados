from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from geopy.geocoders import Nominatim
from geopy.distance import distance
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"
DB_PATH = "clinica.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_user = request.form["login"]
        senha = request.form["senha"]
        conn = get_db_connection()
        medico = conn.execute(
            "SELECT * FROM medico WHERE login=? AND senha=?", (login_user, senha)
        ).fetchone()
        conn.close()
        if medico:
            session["medico"] = medico["id"]
            return redirect(url_for("pacientes"))
        else:
            flash("Login ou senha incorretos!")
    return render_template("login.html")

@app.route("/pacientes")
def pacientes():
    if "medico" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    pendentes = conn.execute("""
        SELECT * FROM pacientes
        WHERE id NOT IN (SELECT id_paciente FROM consulta)
    """).fetchall()

    agendados = conn.execute("""
        SELECT p.*, c.data_hora, u.nome as ubs_nome 
        FROM pacientes p
        JOIN consulta c ON p.id = c.id_paciente
        JOIN ubs u ON c.id_ubs = u.id
        ORDER BY c.data_hora DESC
    """).fetchall()

    conn.close()
    return render_template("pacientes.html", pendentes=pendentes, agendados=agendados)

@app.route("/paciente/<int:id>", methods=["GET", "POST"])
def ver_paciente(id):
    if "medico" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    paciente = conn.execute("SELECT * FROM pacientes WHERE id=?", (id,)).fetchone()

    geolocator = Nominatim(user_agent="clinica_app")
    location = geolocator.geocode(paciente["endereco"])

    if not location:
        flash("Não foi possível localizar o endereço do paciente.")
        ubs_proximas = []
        paciente_coord = None
    else:
        paciente_coord = (location.latitude, location.longitude)
        ubs_list = conn.execute("SELECT * FROM ubs").fetchall()

        ubs_filtradas = []
        visto = set()
        for u in ubs_list:
            if ("UBS" in u["nome"].upper() or "AMA" in u["nome"].upper()):
                chave = (u["nome"], u["endereco"])
                if chave not in visto:
                    ubs_filtradas.append(u)
                    visto.add(chave)

        ubs_proximas = []
        for u in ubs_filtradas:
            try:
                ubs_coord = (float(u["latitude"]), float(u["longitude"]))
                d = distance(paciente_coord, ubs_coord).km
                if d <= 5:
                    ubs_proximas.append((u, d))
            except:
                continue
        ubs_proximas.sort(key=lambda x: x[1])

    if request.method == "POST":
        id_ubs = request.form.get("ubs")
        urgencia = request.form.get("urgencia")

        # Validação: UBS não selecionada
        if not id_ubs:
            flash("❌ Por favor, selecione uma UBS para marcar a consulta!", "error")
            return redirect(url_for("ver_paciente", id=id))

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO consulta (id_paciente, id_ubs, data_hora, urgencia) VALUES (?, ?, ?, ?)",
            (paciente["id"], int(id_ubs), datetime.now(), urgencia)
        )
        conn.commit()
        conn.close()

        flash("✅ Consulta marcada com sucesso!")
        return redirect(url_for("consulta_confirmada", paciente_id=paciente["id"], ubs_id=id_ubs))

    conn.close()
    return render_template(
        "ver_paciente.html",
        paciente=paciente,
        ubs_proximas=ubs_proximas,
        paciente_coord=paciente_coord
    )

@app.route("/consulta_confirmada/<int:paciente_id>/<int:ubs_id>")
def consulta_confirmada(paciente_id, ubs_id):
    if "medico" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    paciente = conn.execute("SELECT * FROM pacientes WHERE id=?", (paciente_id,)).fetchone()
    ubs = conn.execute("SELECT * FROM ubs WHERE id=?", (ubs_id,)).fetchone()
    consulta = conn.execute(
        "SELECT * FROM consulta WHERE id_paciente=? AND id_ubs=? ORDER BY data_hora DESC LIMIT 1",
        (paciente_id, ubs_id)
    ).fetchone()
    conn.close()

    geolocator = Nominatim(user_agent="clinica_app")
    location = geolocator.geocode(paciente["endereco"])
    paciente_coord = (location.latitude, location.longitude) if location else None

    return render_template(
        "consulta_confirmada.html",
        paciente=paciente,
        ubs=ubs,
        consulta=consulta,
        paciente_coord=paciente_coord
    )

@app.route("/logout")
def logout():
    session.pop("medico", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print("⚠️ Banco de dados não encontrado. Execute primeiro o criar_banco.py")
    else:
        app.run(debug=True)
