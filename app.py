import os
import sqlite3
from datetime import datetime, date, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, make_response
)

# --------------------
# CONFIGURACIÓN GENERAL
# --------------------
app = Flask(__name__)
app.secret_key = "miken_prototipo_secret"

DB_NAME = "miken.db"

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTS = {"png", "jpg", "jpeg", "webp"}


# --------------------
# UTILIDADES
# --------------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTS


def db_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Vary"] = "Cookie"
    return response


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return date.today().isoformat()


def parse_date_yyyy_mm_dd(s: str, fallback: str):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except Exception:
        return fallback


# --------------------
# LOGIN / LOGOUT (DEMO)
# --------------------
DEMO_USER = "admin"
DEMO_PASS = "Admin123*"


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pwd = request.form.get("password", "").strip()

        if not user or not pwd:
            flash("Ingrese usuario y contraseña.")
            return redirect(url_for("login"))

        if user == DEMO_USER and pwd == DEMO_PASS:
            session["username"] = user
            return redirect(url_for("dashboard"))

        flash("Usuario o contraseña incorrectos.")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    resp = make_response(redirect(url_for("login")))
    resp.delete_cookie(app.config.get("SESSION_COOKIE_NAME", "session"))
    return resp


# --------------------
# DASHBOARD
# --------------------
@app.route("/dashboard")
@login_required
def dashboard():
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM productos WHERE tipo='maquina'")
    maquinas_total = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) AS c FROM productos WHERE tipo='insumo'")
    insumos_total = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) AS c FROM productos WHERE activo=1")
    activos_total = cur.fetchone()["c"]

    cur.execute("""
        SELECT COUNT(*) AS c
        FROM productos
        WHERE activo=1 AND stock_actual <= stock_min
    """)
    stock_bajo_total = cur.fetchone()["c"]

    # Caja: estado hoy
    dia = today_str()
    cur.execute("SELECT * FROM caja_estado WHERE dia=?", (dia,))
    caja_estado = cur.fetchone()
    caja_abierta = 1 if (caja_estado and caja_estado["abierta"] == 1) else 0

    conn.close()

    return render_template(
        "dashboard.html",
        username=session["username"],
        maquinas_total=maquinas_total,
        insumos_total=insumos_total,
        activos_total=activos_total,
        stock_bajo_total=stock_bajo_total,
        caja_abierta=caja_abierta
    )


# --------------------
# MÓDULO 2: CATÁLOGO
# --------------------
@app.route("/catalogo")
@login_required
def catalogo_home():
    return render_template("catalogo_home.html")


def _listar_catalogo(tipo: str):
    q = request.args.get("q", "").strip()

    conn = db_conn()
    cur = conn.cursor()

    if q:
        cur.execute("""
            SELECT * FROM productos
            WHERE tipo = ?
              AND (sku LIKE ? OR nombre LIKE ? OR categoria LIKE ?)
            ORDER BY id DESC
        """, (tipo, f"%{q}%", f"%{q}%", f"%{q}%"))
    else:
        cur.execute("SELECT * FROM productos WHERE tipo = ? ORDER BY id DESC", (tipo,))

    productos = cur.fetchall()
    conn.close()

    titulo = "Catálogo de Máquinas" if tipo == "maquina" else "Catálogo de Insumos"
    return render_template("catalogo_list.html", productos=productos, q=q, tipo=tipo, titulo=titulo)


@app.route("/catalogo/maquinas")
@login_required
def catalogo_maquinas():
    return _listar_catalogo("maquina")


@app.route("/catalogo/insumos")
@login_required
def catalogo_insumos():
    return _listar_catalogo("insumo")


@app.route("/inventario/stock-bajo")
@login_required
def stock_bajo():
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM productos
        WHERE activo = 1
          AND stock_actual <= stock_min
        ORDER BY tipo, nombre
    """)
    productos = cur.fetchall()
    conn.close()

    return render_template(
        "catalogo_list.html",
        productos=productos,
        q="",
        tipo="todos",
        titulo="⚠ Productos con Stock Bajo"
    )


# --------------------
# CREAR PRODUCTO
# --------------------
@app.route("/catalogo/<tipo>/nuevo", methods=["GET", "POST"])
@login_required
def catalogo_nuevo(tipo):
    if tipo not in ("maquina", "insumo"):
        flash("Catálogo inválido.")
        return redirect(url_for("catalogo_home"))

    if request.method == "POST":
        sku = request.form.get("sku", "").strip()
        nombre = request.form.get("nombre", "").strip()
        categoria = request.form.get("categoria", "").strip()
        unidad = request.form.get("unidad", "").strip()

        precio_raw = request.form.get("precio", "0").strip()
        stock_actual_raw = request.form.get("stock_actual", "0").strip()
        stock_min_raw = request.form.get("stock_min", "0").strip()

        if not nombre:
            flash("El nombre es obligatorio.")
            return redirect(url_for("catalogo_nuevo", tipo=tipo))

        try:
            precio = float(precio_raw) if precio_raw else 0.0
            stock_actual = int(stock_actual_raw) if stock_actual_raw else 0
            stock_min = int(stock_min_raw) if stock_min_raw else 0
        except ValueError:
            flash("Precio o stock inválido. Use números.")
            return redirect(url_for("catalogo_nuevo", tipo=tipo))

        imagen = request.files.get("imagen")
        imagen_filename = None

        if imagen and imagen.filename:
            if not allowed_file(imagen.filename):
                flash("Formato de imagen no permitido (png/jpg/jpeg/webp).")
                return redirect(url_for("catalogo_nuevo", tipo=tipo))

            safe = secure_filename(imagen.filename)
            imagen_filename = f"{tipo}_{nombre[:20].replace(' ','_')}_{safe}"
            imagen.save(os.path.join(UPLOAD_FOLDER, imagen_filename))

        conn = db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO productos
            (tipo, sku, nombre, categoria, unidad, precio, stock_actual, stock_min, imagen_filename, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (tipo, sku, nombre, categoria, unidad, precio, stock_actual, stock_min, imagen_filename))
        conn.commit()
        conn.close()

        flash("Producto creado ✅")
        return redirect(url_for("catalogo_maquinas" if tipo == "maquina" else "catalogo_insumos"))

    return render_template("catalogo_form.html", modo="nuevo", producto=None, tipo=tipo)


# --------------------
# EDITAR PRODUCTO
# --------------------
@app.route("/catalogo/<tipo>/<int:pid>/editar", methods=["GET", "POST"])
@login_required
def catalogo_editar(tipo, pid):
    if tipo not in ("maquina", "insumo"):
        flash("Catálogo inválido.")
        return redirect(url_for("catalogo_home"))

    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM productos WHERE id = ? AND tipo = ?", (pid, tipo))
    producto = cur.fetchone()

    if not producto:
        conn.close()
        flash("Producto no encontrado.")
        return redirect(url_for("catalogo_maquinas" if tipo == "maquina" else "catalogo_insumos"))

    if request.method == "POST":
        sku = request.form.get("sku", "").strip()
        nombre = request.form.get("nombre", "").strip()
        categoria = request.form.get("categoria", "").strip()
        unidad = request.form.get("unidad", "").strip()

        precio_raw = request.form.get("precio", "0").strip()
        stock_actual_raw = request.form.get("stock_actual", "0").strip()
        stock_min_raw = request.form.get("stock_min", "0").strip()

        activo = 1 if request.form.get("activo") == "1" else 0

        if not nombre:
            conn.close()
            flash("El nombre es obligatorio.")
            return redirect(url_for("catalogo_editar", tipo=tipo, pid=pid))

        try:
            precio = float(precio_raw) if precio_raw else 0.0
            stock_actual = int(stock_actual_raw) if stock_actual_raw else 0
            stock_min = int(stock_min_raw) if stock_min_raw else 0
        except ValueError:
            conn.close()
            flash("Precio o stock inválido. Use números.")
            return redirect(url_for("catalogo_editar", tipo=tipo, pid=pid))

        imagen = request.files.get("imagen")
        imagen_filename = producto["imagen_filename"]

        if imagen and imagen.filename:
            if not allowed_file(imagen.filename):
                conn.close()
                flash("Formato de imagen no permitido (png/jpg/jpeg/webp).")
                return redirect(url_for("catalogo_editar", tipo=tipo, pid=pid))

            safe = secure_filename(imagen.filename)
            imagen_filename = f"{tipo}_{nombre[:20].replace(' ','_')}_{safe}"
            imagen.save(os.path.join(UPLOAD_FOLDER, imagen_filename))

        cur.execute("""
            UPDATE productos SET
                sku=?,
                nombre=?,
                categoria=?,
                unidad=?,
                precio=?,
                stock_actual=?,
                stock_min=?,
                imagen_filename=?,
                activo=?
            WHERE id=? AND tipo=?
        """, (sku, nombre, categoria, unidad, precio, stock_actual, stock_min, imagen_filename, activo, pid, tipo))

        conn.commit()
        conn.close()

        flash("Producto actualizado ✅")
        return redirect(url_for("catalogo_maquinas" if tipo == "maquina" else "catalogo_insumos"))

    conn.close()
    return render_template("catalogo_form.html", modo="editar", producto=producto, tipo=tipo)


@app.route("/catalogo/<tipo>/<int:pid>/toggle", methods=["POST"])
@login_required
def catalogo_toggle(tipo, pid):
    if tipo not in ("maquina", "insumo"):
        flash("Catálogo inválido.")
        return redirect(url_for("catalogo_home"))

    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT activo FROM productos WHERE id=? AND tipo=?", (pid, tipo))
    row = cur.fetchone()

    if not row:
        conn.close()
        flash("Producto no encontrado.")
        return redirect(url_for("catalogo_maquinas" if tipo == "maquina" else "catalogo_insumos"))

    nuevo = 0 if row["activo"] == 1 else 1
    cur.execute("UPDATE productos SET activo=? WHERE id=? AND tipo=?", (nuevo, pid, tipo))
    conn.commit()
    conn.close()

    flash("Estado actualizado ✅")
    return redirect(url_for("catalogo_maquinas" if tipo == "maquina" else "catalogo_insumos"))


# ============================================================
# MÓDULO CAJA (Sprint 3): TODO FUNCIONAL
# ============================================================

def ensure_caja_estado(cur, dia: str):
    cur.execute("SELECT * FROM caja_estado WHERE dia=?", (dia,))
    row = cur.fetchone()
    if not row:
        cur.execute("""
            INSERT INTO caja_estado (dia, abierta, efectivo_inicial, created_at)
            VALUES (?, 0, 0, ?)
        """, (dia, now_str()))
        return {"dia": dia, "abierta": 0, "efectivo_inicial": 0}
    return row


def caja_totales(cur, dia: str):
    # Totales efectivo
    cur.execute("""
        SELECT
          COALESCE(SUM(CASE WHEN tipo_mov='ingreso' THEN monto ELSE 0 END),0) AS ing,
          COALESCE(SUM(CASE WHEN tipo_mov='egreso' THEN monto ELSE 0 END),0) AS egr
        FROM caja_movimientos
        WHERE dia=? AND metodo='efectivo'
    """, (dia,))
    r1 = cur.fetchone()

    # Totales banco (solo registro, no saldo real)
    cur.execute("""
        SELECT
          COALESCE(SUM(CASE WHEN tipo_mov='ingreso' THEN monto ELSE 0 END),0) AS ing,
          COALESCE(SUM(CASE WHEN tipo_mov='egreso' THEN monto ELSE 0 END),0) AS egr
        FROM caja_movimientos
        WHERE dia=? AND metodo='banco'
    """, (dia,))
    r2 = cur.fetchone()

    return (r1["ing"], r1["egr"], r2["ing"], r2["egr"])


@app.route("/caja")
@login_required
def caja_home():
    dia = today_str()
    conn = db_conn()
    cur = conn.cursor()

    estado = ensure_caja_estado(cur, dia)

    efectivo_ing, efectivo_egr, banco_ing, banco_egr = caja_totales(cur, dia)

    efectivo_inicial = float(estado["efectivo_inicial"]) if estado else 0.0
    saldo_efectivo = efectivo_inicial + float(efectivo_ing) - float(efectivo_egr)

    # últimos 6 días por defecto
    end = date.today()
    start = end - timedelta(days=5)
    start_s = start.isoformat()
    end_s = end.isoformat()

    cur.execute("""
        SELECT * FROM caja_movimientos
        WHERE date(fecha) BETWEEN ? AND ?
        ORDER BY datetime(fecha) DESC, id DESC
        LIMIT 50
    """, (start_s, end_s))
    ultimos = cur.fetchall()

    conn.commit()
    conn.close()

    return render_template(
        "caja_home.html",
        dia=dia,
        estado=estado,
        efectivo_inicial=efectivo_inicial,
        efectivo_ing=efectivo_ing,
        efectivo_egr=efectivo_egr,
        saldo_efectivo=saldo_efectivo,
        banco_ing=banco_ing,
        banco_egr=banco_egr,
        start=start_s,
        end=end_s,
        ultimos=ultimos
    )


@app.route("/caja/abrir", methods=["GET", "POST"])
@login_required
def caja_abrir():
    dia = today_str()
    conn = db_conn()
    cur = conn.cursor()

    estado = ensure_caja_estado(cur, dia)

    if request.method == "POST":
        efectivo_inicial_raw = request.form.get("efectivo_inicial", "0").strip()
        nota = request.form.get("nota", "").strip()

        try:
            efectivo_inicial = float(efectivo_inicial_raw) if efectivo_inicial_raw else 0.0
        except ValueError:
            flash("Monto inválido.")
            conn.close()
            return redirect(url_for("caja_abrir"))

        # abrir caja (estado)
        cur.execute("""
            UPDATE caja_estado
            SET abierta=1, efectivo_inicial=?
            WHERE dia=?
        """, (efectivo_inicial, dia))

        # registro apertura
        cur.execute("""
            INSERT INTO caja_aperturas (dia, efectivo_inicial, nota, fecha)
            VALUES (?, ?, ?, ?)
        """, (dia, efectivo_inicial, nota, now_str()))

        conn.commit()
        conn.close()

        flash("Caja abierta ✅")
        return redirect(url_for("caja_home"))

    conn.close()
    return render_template("caja_mov_form.html", modo="abrir", dia=dia, estado=estado)


@app.route("/caja/movimiento/nuevo", methods=["GET", "POST"])
@login_required
def caja_mov_nuevo():
    dia_default = today_str()

    if request.method == "POST":
        tipo_mov = request.form.get("tipo_mov", "ingreso").strip()  # ingreso/egreso
        metodo = request.form.get("metodo", "efectivo").strip()     # efectivo/banco
        monto_raw = request.form.get("monto", "0").strip()
        motivo = request.form.get("motivo", "").strip()
        referencia = request.form.get("referencia", "").strip()
        fecha_dia = request.form.get("dia", dia_default).strip()
        fecha_dia = parse_date_yyyy_mm_dd(fecha_dia, dia_default)

        fecha_full = request.form.get("fecha_full", "").strip()  # opcional
        if not fecha_full:
            fecha_full = now_str()
        else:
            # si solo ponen YYYY-MM-DD, le agregamos hora 00:00:00
            if len(fecha_full) == 10:
                fecha_full = fecha_full + " 00:00:00"

        enviado_matriz = 1 if request.form.get("enviado_matriz") == "1" else 0

        # validaciones
        if tipo_mov not in ("ingreso", "egreso"):
            flash("Tipo de movimiento inválido.")
            return redirect(url_for("caja_mov_nuevo"))

        if metodo not in ("efectivo", "banco"):
            flash("Método inválido.")
            return redirect(url_for("caja_mov_nuevo"))

        try:
            monto = float(monto_raw)
            if monto <= 0:
                raise ValueError()
        except ValueError:
            flash("Monto inválido (debe ser mayor a 0).")
            return redirect(url_for("caja_mov_nuevo"))

        # Si es banco, referencia (comprobante) recomendado
        if metodo == "banco" and not referencia:
            flash("En pagos por banco, ingrese el número de comprobante (referencia).")
            return redirect(url_for("caja_mov_nuevo"))

        conn = db_conn()
        cur = conn.cursor()

        # asegurar estado del día (por si registras movimientos de días anteriores)
        ensure_caja_estado(cur, fecha_dia)

        cur.execute("""
            INSERT INTO caja_movimientos
            (fecha, dia, monto, motivo, referencia, tipo_mov, metodo, enviado_matriz)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (fecha_full, fecha_dia, monto, motivo, referencia, tipo_mov, metodo, enviado_matriz))

        conn.commit()
        conn.close()

        flash("Movimiento registrado ✅")
        return redirect(url_for("caja_home"))

    return render_template("caja_mov_form.html", modo="mov", dia=dia_default, estado=None)


@app.route("/caja/movimientos")
@login_required
def caja_movimientos_list():
    # filtro por fechas (por defecto 6 días)
    end = request.args.get("end", "").strip()
    start = request.args.get("start", "").strip()
    metodo = request.args.get("metodo", "todos").strip()

    today = date.today()
    if not end:
        end = today.isoformat()
    end = parse_date_yyyy_mm_dd(end, today.isoformat())

    if not start:
        start = (today - timedelta(days=5)).isoformat()
    start = parse_date_yyyy_mm_dd(start, (today - timedelta(days=5)).isoformat())

    conn = db_conn()
    cur = conn.cursor()

    params = [start, end]
    where_extra = ""

    if metodo in ("efectivo", "banco"):
        where_extra = " AND metodo=? "
        params.append(metodo)

    cur.execute(f"""
        SELECT * FROM caja_movimientos
        WHERE date(fecha) BETWEEN ? AND ?
        {where_extra}
        ORDER BY datetime(fecha) DESC, id DESC
    """, tuple(params))
    rows = cur.fetchall()

    # Totales visibles arriba: Ingresos / Egresos
    cur.execute(f"""
        SELECT
          COALESCE(SUM(CASE WHEN tipo_mov='ingreso' THEN monto ELSE 0 END),0) AS ing,
          COALESCE(SUM(CASE WHEN tipo_mov='egreso' THEN monto ELSE 0 END),0) AS egr
        FROM caja_movimientos
        WHERE date(fecha) BETWEEN ? AND ?
        {where_extra}
    """, tuple(params))
    t = cur.fetchone()

    conn.close()

    return render_template(
        "caja_movimientos_list.html",
        rows=rows,
        start=start,
        end=end,
        metodo=metodo,
        total_ing=float(t["ing"]),
        total_egr=float(t["egr"])
    )


@app.route("/caja/movimiento/<int:mid>/enviar-matriz", methods=["POST"])
@login_required
def caja_marcar_enviado_matriz(mid):
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("UPDATE caja_movimientos SET enviado_matriz=1 WHERE id=?", (mid,))
    conn.commit()
    conn.close()

    flash("Marcado como enviado a matriz ✅")
    return redirect(url_for("caja_movimientos_list"))


@app.route("/caja/cerrar", methods=["GET", "POST"])
@login_required
def caja_cerrar():
    dia = today_str()
    conn = db_conn()
    cur = conn.cursor()

    estado = ensure_caja_estado(cur, dia)

    if estado and int(estado["abierta"]) != 1:
        conn.close()
        flash("La caja no está abierta hoy.")
        return redirect(url_for("caja_home"))

    efectivo_ing, efectivo_egr, _, _ = caja_totales(cur, dia)
    efectivo_inicial = float(estado["efectivo_inicial"]) if estado else 0.0
    efectivo_final = efectivo_inicial + float(efectivo_ing) - float(efectivo_egr)

    if request.method == "POST":
        nota = request.form.get("nota", "").strip()

        cur.execute("""
            INSERT INTO caja_cierres
            (dia, efectivo_final, total_ingresos, total_egresos, nota, fecha)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (dia, efectivo_final, float(efectivo_ing), float(efectivo_egr), nota, now_str()))

        cur.execute("""
            UPDATE caja_estado
            SET abierta=0
            WHERE dia=?
        """, (dia,))

        conn.commit()
        conn.close()

        flash("Caja cerrada ✅")
        return redirect(url_for("caja_home"))

    conn.close()
    return render_template(
        "caja_cierre.html",
        dia=dia,
        efectivo_inicial=efectivo_inicial,
        efectivo_ing=efectivo_ing,
        efectivo_egr=efectivo_egr,
        efectivo_final=efectivo_final
    )


# --------------------
# MAIN
# --------------------
if __name__ == "__main__":
    app.run(debug=True)
