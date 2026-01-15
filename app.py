import os
import sqlite3
from datetime import datetime, date, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, make_response
)

CATEGORIAS_MAQUINAS = [
    "Helado soft", "Helado artesanal", "Granizadora", "Milkshake",
    "Waflera", "Crepera", "Donas", "Congelador", "Regulador", "Otros"
]
CATEGORIAS_INSUMOS = [
    "Bases", "Conos", "Tarrinas", "Vasos", "Toppings", "Repuestos", "Otros"
]
UNIDADES = ["unidad", "caja", "paquete", "kit", "bolsa", "litro", "kilogramo"]

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
    # habilitar FK por conexión (útil si tienes foreign keys)
    conn.execute("PRAGMA foreign_keys = ON;")
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

    return render_template("login.html", hide_nav=True, page_class="page-login", title="MIKEN - Iniciar sesión")




@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Vary"] = "Cookie"
    return response


@app.route("/logout")
def logout():
    session.clear()
    resp = make_response(redirect(url_for("login")))
    resp.delete_cookie(app.config.get("SESSION_COOKIE_NAME", "session"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp




# --------------------
# DASHBOARD (Sprint 4)
# --------------------
@app.route("/dashboard")
@login_required
def dashboard():
    conn = db_conn()
    cur = conn.cursor()

    # KPIs de productos (ACTIVOS)
    cur.execute("SELECT COUNT(*) AS c FROM productos WHERE activo=1")
    total_productos = cur.fetchone()["c"]

    cur.execute("""
        SELECT COUNT(*) AS c
        FROM productos
        WHERE activo=1 AND stock_actual <= stock_min
    """)
    bajo_stock = cur.fetchone()["c"]

    # Estado Operativo (proxy: activo=1 operativa, activo=0 en revisión) para tipo='maquina'
    cur.execute("SELECT COUNT(*) AS c FROM productos WHERE tipo='maquina'")
    maquinas_total = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) AS c FROM productos WHERE tipo='maquina' AND activo=1")
    maquinas_operativas = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) AS c FROM productos WHERE tipo='maquina' AND activo=0")
    maquinas_revision = cur.fetchone()["c"]

    # Caja: estado hoy
    dia = today_str()
    cur.execute("SELECT * FROM caja_estado WHERE dia=?", (dia,))
    estado = cur.fetchone()
    caja_abierta = 1 if (estado and int(estado["abierta"]) == 1) else 0
    efectivo_inicial = float(estado["efectivo_inicial"]) if estado else 0.0

    # Caja chica hoy: efectivo_inicial + ingresos_efectivo - egresos_efectivo
    cur.execute("""
        SELECT
          COALESCE(SUM(CASE WHEN tipo_mov='ingreso' THEN monto ELSE 0 END),0) AS ing,
          COALESCE(SUM(CASE WHEN tipo_mov='egreso' THEN monto ELSE 0 END),0) AS egr
        FROM caja_movimientos
        WHERE dia=? AND metodo='efectivo'
    """, (dia,))
    r = cur.fetchone()
    ingresos_hoy = float(r["ing"]) if r else 0.0
    egresos_hoy = float(r["egr"]) if r else 0.0
    caja_chica = efectivo_inicial + ingresos_hoy - egresos_hoy

    # Último reporte: última fecha remembered de caja_movimientos o NOW
    cur.execute("SELECT MAX(fecha) AS last FROM caja_movimientos")
    last = cur.fetchone()["last"]
    ultimo_reporte = last if last else now_str()

    # Existencias insumos (agrupado por categoria)
    cur.execute("""
        SELECT categoria, nombre, stock_actual, stock_min
        FROM productos
        WHERE tipo='insumo' AND activo=1
        ORDER BY COALESCE(categoria,''), nombre
    """)
    rows = cur.fetchall()

    existencias = []
    grupo_actual = None
    bucket = None

    for row in rows:
        grupo = row["categoria"] if row["categoria"] else "Insumos"

        if grupo != grupo_actual:
            if bucket:
                existencias.append(bucket)
            bucket = {"grupo": grupo, "items": []}
            grupo_actual = grupo

        stock = int(row["stock_actual"]) if row["stock_actual"] is not None else 0
        min_stock = int(row["stock_min"]) if row["stock_min"] is not None else 0

        bucket["items"].append({
            "nombre": row["nombre"],
            "stock": stock,
            "bajo": stock <= min_stock
        })

    if bucket:
        existencias.append(bucket)

    # Máquinas (lista top 6)
    cur.execute("""
        SELECT nombre
        FROM productos
        WHERE tipo='maquina'
        ORDER BY id DESC
        LIMIT 6
    """)
    maquinas = [{"modelo": m["nombre"], "cliente": "aqui va el nombre del cliente"} for m in cur.fetchall()]

    conn.close()

    estado_operativa_texto = (
        f"{maquinas_revision} máquina en revisión"
        if maquinas_revision == 1
        else f"{maquinas_revision} máquinas en revisión"
    )

    return render_template(
        "dashboard.html",
        username=session["username"],
        total_productos=total_productos,
        bajo_stock=bajo_stock,
        caja_chica=caja_chica,
        ingresos_hoy=ingresos_hoy,
        caja_abierta=caja_abierta,
        ultimo_reporte=ultimo_reporte,
        existencias=existencias,
        maquinas_total=maquinas_total,
        maquinas_operativas=maquinas_operativas,
        maquinas_revision=maquinas_revision,
        estado_operativa_texto=estado_operativa_texto,
        maquinas=maquinas
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
    page = request.args.get("page", "1").strip()

    try:
        page = int(page)
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    per_page = 6
    offset = (page - 1) * per_page

    conn = db_conn()
    cur = conn.cursor()

    where = "WHERE tipo = ?"
    params = [tipo]

    if q:
        where += " AND (sku LIKE ? OR nombre LIKE ? OR categoria LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]

    # total para paginación
    cur.execute(f"SELECT COUNT(*) AS c FROM productos {where}", tuple(params))
    total = cur.fetchone()["c"]

    # filas
    cur.execute(f"""
        SELECT id, sku, nombre, categoria, stock_actual, stock_min, imagen_filename, activo
        FROM productos
        {where}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, tuple(params + [per_page, offset]))
    productos = cur.fetchall()
    conn.close()

    total_pages = (total + per_page - 1) // per_page

    titulo = "Catálogo de Máquinas" if tipo == "maquina" else "Catálogo de Insumos"

    return render_template(
        "catalogo_list.html",
        productos=productos,
        q=q,
        tipo=tipo,
        titulo=titulo,
        page=page,
        total_pages=total_pages,
        total=total
    )



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
    q = request.args.get("q", "").strip()
    page = request.args.get("page", "1").strip()

    try:
        page = int(page)
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    per_page = 6
    offset = (page - 1) * per_page

    conn = db_conn()
    cur = conn.cursor()

    where = "WHERE activo=1 AND stock_actual <= stock_min"
    params = []

    if q:
        where += " AND (sku LIKE ? OR nombre LIKE ? OR categoria LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]

    cur.execute(f"SELECT COUNT(*) AS c FROM productos {where}", tuple(params))
    total = cur.fetchone()["c"]

    cur.execute(f"""
        SELECT id, tipo, sku, nombre, categoria, stock_actual, stock_min, imagen_filename, activo
        FROM productos
        {where}
        ORDER BY tipo, nombre
        LIMIT ? OFFSET ?
    """, tuple(params + [per_page, offset]))
    productos = cur.fetchall()
    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template(
        "catalogo_list.html",
        productos=productos,
        q=q,
        tipo="todos",
        titulo="⚠ Productos con Stock Bajo",
        page=page,
        total_pages=total_pages,
        total=total
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

    cats = CATEGORIAS_MAQUINAS if tipo=="maquina" else CATEGORIAS_INSUMOS
    return render_template("catalogo_form.html", modo="nuevo", producto=None, tipo=tipo, categorias=cats, unidades=UNIDADES)



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

    cats = CATEGORIAS_MAQUINAS if tipo=="maquina" else CATEGORIAS_INSUMOS
    return render_template("catalogo_form.html", modo="editar", producto=producto, tipo=tipo, categorias=cats, unidades=UNIDADES)



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
# MÓDULO CAJA (Sprint 3): FUNCIONAL
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

    # Totales banco
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

        cur.execute("""
            UPDATE caja_estado
            SET abierta=1, efectivo_inicial=?
            WHERE dia=?
        """, (efectivo_inicial, dia))

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
        tipo_mov = request.form.get("tipo_mov", "ingreso").strip()
        metodo = request.form.get("metodo", "efectivo").strip()
        monto_raw = request.form.get("monto", "0").strip()
        motivo = request.form.get("motivo", "").strip()
        referencia = request.form.get("referencia", "").strip()
        fecha_dia = request.form.get("dia", dia_default).strip()
        fecha_dia = parse_date_yyyy_mm_dd(fecha_dia, dia_default)

        fecha_full = request.form.get("fecha_full", "").strip()
        if not fecha_full:
            fecha_full = now_str()
        else:
            if len(fecha_full) == 10:
                fecha_full = fecha_full + " 00:00:00"

        enviado_matriz = 1 if request.form.get("enviado_matriz") == "1" else 0

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

        if metodo == "banco" and not referencia:
            flash("En pagos por banco, ingrese el número de comprobante (referencia).")
            return redirect(url_for("caja_mov_nuevo"))

        conn = db_conn()
        cur = conn.cursor()

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

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    # Si ya hay sesión, igual puede recuperar contraseña, pero normalmente lo mandamos al dashboard
    if "username" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        correo = request.form.get("email", "").strip()

        if not correo:
            flash("Ingrese su correo para recuperar la contraseña.")
            return redirect(url_for("forgot_password"))

        # Demo: NO enviamos correo real en este prototipo
        flash("✅ Solicitud enviada. MIKEN se contactará desde miken.heladeria@gmail.com.")
        return redirect(url_for("login"))

    return render_template("forgot_password.html", hide_nav=True, page_class="page-login", title="MIKEN - Recuperar contraseña")





# --------------------
# MAIN
# --------------------
if __name__ == "__main__":
    app.run(debug=True)
