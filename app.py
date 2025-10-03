from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3
from geopy.geocoders import Nominatim
from geopy.distance import distance
from datetime import datetime
import os
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

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
        data_consulta = request.form.get("data_consulta")
        hora_consulta = request.form.get("hora_consulta")

        if not id_ubs or not data_consulta or not hora_consulta:
            flash("❌ Preencha todos os campos!", "error")
            return redirect(url_for("ver_paciente", id=id))

        data_hora = f"{data_consulta} {hora_consulta}:00"

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO consulta (id_paciente, id_ubs, data_hora, urgencia) VALUES (?, ?, ?, ?)",
            (paciente["id"], int(id_ubs), data_hora, urgencia)
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

@app.route("/gerar_atestado/<int:paciente_id>", methods=["GET", "POST"])
def gerar_atestado(paciente_id):
    if "medico" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    paciente = conn.execute("SELECT * FROM pacientes WHERE id=?", (paciente_id,)).fetchone()
    consulta = conn.execute("""
        SELECT * FROM consulta WHERE id_paciente=? ORDER BY data_hora DESC LIMIT 1
    """, (paciente_id,)).fetchone()
    conn.close()

    if request.method == "POST":
        descricao = request.form.get("descricao", "Atestado Médico")
        nome_medico = request.form.get("nome_medico", "Médico não informado")

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        left_margin = 50
        top_margin = height - 50
        c.setLineWidth(2)
        c.rect(30, 30, width-60, height-60)
        logo_path = "static/logo.png"  # Coloque sua logo em /static/logo.png
        if os.path.exists(logo_path):
            c.drawImage(logo_path, width/2 - 50, top_margin - 80, width=100, preserveAspectRatio=True, mask='auto')

        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(width / 2, top_margin - 120, "ATESTADO MÉDICO")
        y = top_margin - 160
        c.setFont("Helvetica-Bold", 12)
        c.drawString(left_margin, y, f"Paciente: {paciente['nome']}")
        y -= 20
        c.drawString(left_margin, y, f"Idade: {paciente['idade']}")
        y -= 20
        c.drawString(left_margin, y, f"Endereço: {paciente['endereco']}")
        if consulta:
            y -= 30
            c.setFont("Helvetica", 12)
            c.drawString(left_margin, y, f"Data/Hora da Consulta: {consulta['data_hora']}")
            y -= 20
            c.drawString(left_margin, y, f"Urgência: {consulta['urgencia']}")
        y -= 40
        caixa_altura = 60  # altura do retângulo
        c.setStrokeColorRGB(0.2, 0.2, 0.2)
        c.setFillColorRGB(0.95, 0.95, 0.95)
        c.rect(left_margin - 5, y - caixa_altura, width - left_margin * 2 + 10, caixa_altura, fill=1)
        c.setFillColorRGB(0,0,0)
        text = c.beginText(left_margin + 5, y - 20)  # +5 para margem interna
        text.setFont("Helvetica", 12)
        text.textLines(descricao)
        c.drawText(text)
        c.line(width-300, 120, width-100, 120)
        c.setFont("Helvetica", 12)
        c.drawString(width-300, 100, f"Médico: {nome_medico}")
        c.setFont("Helvetica-Oblique", 10)
        c.drawCentredString(width/2, 50, "Atestado válido mediante conferência dos dados e assinatura do médico.")

        c.showPage()
        c.save()
        buffer.seek(0)

        return send_file(buffer, as_attachment=True, download_name=f"Atestado_{paciente['nome']}.pdf", mimetype='application/pdf')

    return render_template("atestado_form.html", paciente=paciente)


@app.route("/logout")
def logout():
    session.pop("medico", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print("⚠️ Banco de dados não encontrado. Execute primeiro o criar_banco.py")
    else:
        app.run(debug=True)