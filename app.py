import os
import sqlite3
from datetime import datetime, date, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, make_response, jsonify
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
    conn = sqlite3.connect(
        DB_NAME,
        timeout=30,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
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


def parse_datetime_input(s: str, fallback: str):
    """
    Acepta:
      - '' => fallback
      - 'YYYY-MM-DD' => agrega 00:00:00
      - 'YYYY-MM-DD HH:MM:SS' => ok
      - 'YYYY-MM-DD HH:MM' => agrega :00
    """
    s = (s or "").strip()
    if not s:
        return fallback

    if len(s) == 10:
        return s + " 00:00:00"
    if len(s) == 16:
        return s + ":00"
    return s


def table_info(cur, table: str):
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def table_has_column(cur, table: str, column: str) -> bool:
    cols = table_info(cur, table)
    return column in cols


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def caja_col_medio(cur) -> str:
    # Tu BD puede tener 'medio' o 'metodo'. En tu db.py actual (el que debes usar) existen ambos,
    # pero dejamos esto por compatibilidad.
    if table_has_column(cur, "caja_movimientos", "medio"):
        return "medio"
    return "metodo"


def caja_col_fecha(cur) -> str:
    # Preferimos fecha_full (si existe) y si no, fecha.
    if table_has_column(cur, "caja_movimientos", "fecha_full"):
        return "fecha_full"
    return "fecha"


def caja_fecha_expr(cur) -> str:
    # Para filtrar correctamente por fecha, usamos COALESCE(fecha_full, fecha) si existe.
    has_ff = table_has_column(cur, "caja_movimientos", "fecha_full")
    if has_ff:
        return "COALESCE(fecha_full, fecha)"
    return "fecha"


def insert_caja_movimiento(cur, data: dict) -> int:
    """
    Inserta movimiento en caja_movimientos de forma robusta según columnas existentes.
    Retorna el id del movimiento insertado.
    """
    cols = table_info(cur, "caja_movimientos")

    # Campos que queremos insertar (si existen)
    desired = {
        "fecha": data.get("fecha"),
        "fecha_full": data.get("fecha_full"),
        "dia": data.get("dia"),
        "monto": data.get("monto", 0),
        "motivo": data.get("motivo"),
        "referencia": data.get("referencia"),
        "tipo_mov": data.get("tipo_mov", "ingreso"),
        "metodo": data.get("metodo", "efectivo"),
        "medio": data.get("metodo", "efectivo"),  # compat
        "enviado_matriz": data.get("enviado_matriz", 0),
        "destino_otro": data.get("destino_otro"),
        "comprobante": data.get("comprobante"),
        "banco_nombre": data.get("banco_nombre"),
        "tipo": data.get("tipo_mov", "ingreso"),  # compat
    }

    insert_cols = [c for c in desired.keys() if c in cols and desired[c] is not None]
    if not insert_cols:
        raise RuntimeError("No hay columnas compatibles para insertar en caja_movimientos.")

    placeholders = ",".join(["?"] * len(insert_cols))
    sql = f"INSERT INTO caja_movimientos ({','.join(insert_cols)}) VALUES ({placeholders})"
    cur.execute(sql, tuple(desired[c] for c in insert_cols))
    return int(cur.lastrowid)


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
# DASHBOARD (Sprint 4 UI)
# --------------------
@app.route("/dashboard")
@login_required
def dashboard():
    dia = today_str()

    conn = db_conn()
    cur = conn.cursor()

    # ====== KPIs TOP ======
    cur.execute("SELECT COUNT(*) AS c FROM productos WHERE activo=1")
    total_productos = cur.fetchone()["c"]

    cur.execute("""
        SELECT COUNT(*) AS c
        FROM productos
        WHERE activo=1 AND tipo='insumo' AND stock_actual <= stock_min
    """)
    bajo_insumos = cur.fetchone()["c"]

    cur.execute("""
        SELECT COUNT(*) AS c
        FROM productos
        WHERE activo=1 AND tipo='maquina' AND stock_actual <= stock_min
    """)
    bajo_maquinas = cur.fetchone()["c"]

    # ====== Caja chica (visual) ======
    cur.execute("SELECT * FROM caja_estado WHERE dia=?", (dia,))
    caja_estado = cur.fetchone()
    caja_abierta = 1 if (caja_estado and int(caja_estado["abierta"]) == 1) else 0

    efectivo_inicial = float(caja_estado["efectivo_inicial"]) if caja_estado else 0.0
    cur.execute("""
        SELECT
          COALESCE(SUM(CASE WHEN tipo_mov='ingreso' THEN monto ELSE 0 END),0) AS ing,
          COALESCE(SUM(CASE WHEN tipo_mov='egreso' THEN monto ELSE 0 END),0) AS egr
        FROM caja_movimientos
        WHERE dia=? AND metodo='efectivo'
    """, (dia,))
    t = cur.fetchone()
    saldo_caja = efectivo_inicial + float(t["ing"]) - float(t["egr"])

    # ====== Ventas de hoy (por caja_movimientos) ======
    cur.execute("""
        SELECT
            COALESCE(SUM(monto), 0) AS total,
            COUNT(*) AS n
        FROM caja_movimientos
        WHERE dia = ?
          AND tipo_mov = 'ingreso'
          AND LOWER(COALESCE(motivo,'')) LIKE '%venta%'
    """, (dia,))
    v = cur.fetchone()
    ventas_hoy_total = float(v["total"])
    ventas_hoy_n = int(v["n"])

    # ====== EXISTENCIAS INSUMOS (panel) ======
    cur.execute("""
        SELECT id, sku, nombre, categoria, stock_actual, stock_min
        FROM productos
        WHERE activo=1 AND tipo='insumo'
        ORDER BY
            CASE WHEN stock_actual <= stock_min THEN 0 ELSE 1 END,
            COALESCE(categoria,''), nombre
        LIMIT 30
    """)
    insumos_rows = cur.fetchall()

    # =========================================================
    # ✅ NUEVO: Ventas SEMANALES (Lunes a Sábado) + Top vendidos
    # =========================================================
    today = date.today()
    week_start = today - timedelta(days=today.weekday())     # Lunes
    week_end = week_start + timedelta(days=5)               # Sábado

    week_start_s = week_start.isoformat()
    week_end_s = week_end.isoformat()

    # Ventas por día (caja_movimientos)
    cur.execute("""
        SELECT dia, COALESCE(SUM(monto),0) AS total
        FROM caja_movimientos
        WHERE dia BETWEEN ? AND ?
          AND tipo_mov='ingreso'
          AND LOWER(COALESCE(motivo,'')) LIKE '%venta%'
        GROUP BY dia
        ORDER BY dia
    """, (week_start_s, week_end_s))
    rows_week = cur.fetchall()

    totals_map = {r["dia"]: float(r["total"]) for r in rows_week}
    week_days = []
    week_labels = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]
    week_total = 0.0

    for i in range(6):
        d = (week_start + timedelta(days=i)).isoformat()
        val = float(totals_map.get(d, 0.0))
        week_total += val
        week_days.append({"dia": d, "label": week_labels[i], "total": val})

    # Semana anterior (para ver tendencia)
    prev_start = week_start - timedelta(days=7)
    prev_end = prev_start + timedelta(days=5)
    prev_start_s = prev_start.isoformat()
    prev_end_s = prev_end.isoformat()

    cur.execute("""
        SELECT COALESCE(SUM(monto),0) AS total
        FROM caja_movimientos
        WHERE dia BETWEEN ? AND ?
          AND tipo_mov='ingreso'
          AND LOWER(COALESCE(motivo,'')) LIKE '%venta%'
    """, (prev_start_s, prev_end_s))
    prev_week_total = float(cur.fetchone()["total"] or 0)

    if prev_week_total <= 0 and week_total > 0:
        trend = "up"
        trend_pct = 100.0
    elif prev_week_total <= 0 and week_total <= 0:
        trend = "flat"
        trend_pct = 0.0
    else:
        delta = week_total - prev_week_total
        trend_pct = round((delta / prev_week_total) * 100, 1)
        if delta > 0:
            trend = "up"
        elif delta < 0:
            trend = "down"
        else:
            trend = "flat"

    # Top vendido INSUMO (desde movimientos)
    cur.execute("""
        SELECT p.id, p.sku, p.nombre, SUM(m.cantidad) AS qty
        FROM movimientos m
        JOIN productos p ON p.id = m.producto_id
        WHERE p.tipo='insumo'
          AND m.tipo_mov='egreso'
          AND LOWER(COALESCE(m.motivo,'')) LIKE '%venta%'
          AND date(m.fecha) BETWEEN ? AND ?
        GROUP BY p.id
        ORDER BY qty DESC
        LIMIT 1
    """, (week_start_s, week_end_s))
    top_insumo = cur.fetchone()

    # Top vendido MAQUINA (desde movimientos)
    cur.execute("""
        SELECT p.id, p.sku, p.nombre, SUM(m.cantidad) AS qty
        FROM movimientos m
        JOIN productos p ON p.id = m.producto_id
        WHERE p.tipo='maquina'
          AND m.tipo_mov='egreso'
          AND LOWER(COALESCE(m.motivo,'')) LIKE '%venta%'
          AND date(m.fecha) BETWEEN ? AND ?
        GROUP BY p.id
        ORDER BY qty DESC
        LIMIT 1
    """, (week_start_s, week_end_s))
    top_maquina = cur.fetchone()

    conn.close()

    return render_template(
        "dashboard.html",
        username=session["username"],
        total_productos=total_productos,
        bajo_insumos=bajo_insumos,
        bajo_maquinas=bajo_maquinas,
        saldo_caja=saldo_caja,
        caja_abierta=caja_abierta,
        ventas_hoy_total=ventas_hoy_total,
        ventas_hoy_n=ventas_hoy_n,
        insumos_rows=insumos_rows,
        ultimo_reporte=now_str(),

        # NUEVO
        week_start=week_start_s,
        week_end=week_end_s,
        week_days=week_days,
        week_total=week_total,
        prev_week_total=prev_week_total,
        trend=trend,
        trend_pct=trend_pct,
        top_insumo=top_insumo,
        top_maquina=top_maquina,
    )

# --------------------
# REPORTES (CSV)
# --------------------
@app.route("/reportes/ventas.csv")
@login_required
def reporte_ventas_csv():
    conn = db_conn()
    cur = conn.cursor()

    fecha_expr = caja_fecha_expr(cur)

    cur.execute(f"""
        SELECT fecha, fecha_full, dia, monto, motivo, metodo, medio, referencia, tipo_mov
        FROM caja_movimientos
        WHERE tipo_mov='ingreso'
        ORDER BY datetime({fecha_expr}) DESC, id DESC
    """)
    rows = cur.fetchall()
    conn.close()

    lines = ["fecha,dia,monto,motivo,metodo,referencia"]
    for r in rows:
        fecha_val = r["fecha_full"] or r["fecha"] or ""
        fecha_val = fecha_val.replace(",", " ")
        dia = (r["dia"] or "").replace(",", " ")
        monto = str(r["monto"] if r["monto"] is not None else 0)
        # preferimos metodo; si no, medio
        metodo = (r["metodo"] or r["medio"] or "").replace(",", " ")
        motivo = (r["motivo"] or "").replace(",", " ")
        referencia = (r["referencia"] or "").replace(",", " ")
        lines.append(f"{fecha_val},{dia},{monto},{motivo},{metodo},{referencia}")

    csv_data = "\n".join(lines)
    resp = make_response(csv_data)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=reporte_ventas.csv"
    return resp


@app.route("/reportes/inventario.csv")
@login_required
def reporte_inventario_csv():
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT tipo, sku, nombre, categoria, unidad, precio, stock_actual, stock_min, activo
        FROM productos
        ORDER BY tipo, COALESCE(categoria,''), nombre
    """)
    rows = cur.fetchall()
    conn.close()

    lines = ["tipo,sku,nombre,categoria,unidad,precio,stock_actual,stock_min,activo"]
    for r in rows:
        tipo = (r["tipo"] or "").replace(",", " ")
        sku = (r["sku"] or "").replace(",", " ")
        nombre = (r["nombre"] or "").replace(",", " ")
        categoria = (r["categoria"] or "").replace(",", " ")
        unidad = (r["unidad"] or "").replace(",", " ")
        precio = str(r["precio"] if r["precio"] is not None else 0)
        stock_actual = str(r["stock_actual"] if r["stock_actual"] is not None else 0)
        stock_min = str(r["stock_min"] if r["stock_min"] is not None else 0)
        activo = str(r["activo"] if r["activo"] is not None else 0)
        lines.append(f"{tipo},{sku},{nombre},{categoria},{unidad},{precio},{stock_actual},{stock_min},{activo}")

    csv_data = "\n".join(lines)
    resp = make_response(csv_data)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=reporte_inventario.csv"
    return resp


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

    cur.execute(f"SELECT COUNT(*) AS c FROM productos {where}", tuple(params))
    total = cur.fetchone()["c"]

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

    cats = CATEGORIAS_MAQUINAS if tipo == "maquina" else CATEGORIAS_INSUMOS
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

    cats = CATEGORIAS_MAQUINAS if tipo == "maquina" else CATEGORIAS_INSUMOS
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
# MÓDULO CAJA (Sprint 3): FUNCIONAL + ITEMS (VENTA)
# ============================================================
def ensure_caja_estado(cur, dia: str):
    dia = parse_date_yyyy_mm_dd(dia, today_str())

    cur.execute("SELECT * FROM caja_estado WHERE dia=?", (dia,))
    row = cur.fetchone()
    if row:
        return row

    cur.execute("""
        INSERT INTO caja_estado (dia, abierta, efectivo_inicial, created_at)
        VALUES (?, 0, 0, ?)
    """, (dia, now_str()))

    cur.execute("SELECT * FROM caja_estado WHERE dia=?", (dia,))
    return cur.fetchone()


def caja_totales(cur, dia: str):
    medio_col = caja_col_medio(cur)

    # Totales efectivo
    cur.execute(f"""
        SELECT
          COALESCE(SUM(CASE WHEN tipo_mov='ingreso' THEN monto ELSE 0 END),0) AS ing,
          COALESCE(SUM(CASE WHEN tipo_mov='egreso' THEN monto ELSE 0 END),0) AS egr
        FROM caja_movimientos
        WHERE dia=? AND {medio_col}='efectivo'
    """, (dia,))
    r1 = cur.fetchone()

    # Totales banco
    cur.execute(f"""
        SELECT
          COALESCE(SUM(CASE WHEN tipo_mov='ingreso' THEN monto ELSE 0 END),0) AS ing,
          COALESCE(SUM(CASE WHEN tipo_mov='egreso' THEN monto ELSE 0 END),0) AS egr
        FROM caja_movimientos
        WHERE dia=? AND {medio_col}='banco'
    """, (dia,))
    r2 = cur.fetchone()

    return (r1["ing"], r1["egr"], r2["ing"], r2["egr"])


@app.route("/caja")
@login_required
def caja_home():
    dia = today_str()
    conn = db_conn()
    try:
        cur = conn.cursor()
        estado = ensure_caja_estado(cur, dia)

        efectivo_ing, efectivo_egr, banco_ing, banco_egr = caja_totales(cur, dia)

        efectivo_inicial = float(estado["efectivo_inicial"]) if estado else 0.0
        saldo_efectivo = efectivo_inicial + float(efectivo_ing) - float(efectivo_egr)

        end = date.today()
        start = end - timedelta(days=5)
        start_s = start.isoformat()
        end_s = end.isoformat()

        fecha_expr = caja_fecha_expr(cur)

        cur.execute(f"""
            SELECT * FROM caja_movimientos
            WHERE date({fecha_expr}) BETWEEN ? AND ?
            ORDER BY datetime({fecha_expr}) DESC, id DESC
            LIMIT 50
        """, (start_s, end_s))
        ultimos = cur.fetchall()

        conn.commit()

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
    finally:
        conn.close()


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
    return render_template("caja_mov_form.html", modo="abrir", dia=dia, estado=estado, page_class="page-wide")


# -------------------------
# API: buscar productos (para autocompletar en movimientos)
# -------------------------
@app.route("/api/productos/buscar")
@login_required
def api_productos_buscar():
    q = (request.args.get("q", "") or "").strip()
    tipo = (request.args.get("tipo", "") or "").strip()  # opcional: insumo/maquina
    limit = 15

    conn = db_conn()
    cur = conn.cursor()

    where = "WHERE activo=1"
    params = []

    if tipo in ("insumo", "maquina"):
        where += " AND tipo=?"
        params.append(tipo)

    if q:
        where += " AND (sku LIKE ? OR nombre LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]

    cur.execute(f"""
        SELECT id, tipo, sku, nombre, categoria, unidad, precio, stock_actual, stock_min
        FROM productos
        {where}
        ORDER BY
          CASE WHEN stock_actual <= stock_min THEN 0 ELSE 1 END,
          nombre
        LIMIT ?
    """, tuple(params + [limit]))
    rows = cur.fetchall()
    conn.close()

    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "tipo": r["tipo"],
            "sku": r["sku"] or "",
            "nombre": r["nombre"] or "",
            "categoria": r["categoria"] or "",
            "unidad": r["unidad"] or "",
            "precio": float(r["precio"] or 0),
            "stock_actual": int(r["stock_actual"] or 0),
            "stock_min": int(r["stock_min"] or 0),
        })
    return jsonify(out)


# -------------------------
# NUEVO MOVIMIENTO (Caja + Venta por items)
# -------------------------
@app.route("/caja/movimiento/nuevo", methods=["GET", "POST"])
@login_required
def caja_mov_nuevo():
    dia_default = today_str()

    if request.method == "POST":
        # ---------- inputs base ----------
        tipo_mov = (request.form.get("tipo_mov", "ingreso") or "ingreso").strip().lower()

        # acepta metodo (nuevo) o medio (viejo)
        metodo = (request.form.get("metodo") or request.form.get("medio") or "efectivo").strip().lower()

        monto_raw = (request.form.get("monto", "0") or "0").strip()
        motivo = (request.form.get("motivo", "") or "").strip()
        referencia = (request.form.get("referencia", "") or "").strip()

        fecha_dia = (request.form.get("dia", dia_default) or dia_default).strip()
        fecha_dia = parse_date_yyyy_mm_dd(fecha_dia, dia_default)

        fecha_full_in = (request.form.get("fecha_full", "") or "").strip()
        fecha_full = parse_datetime_input(fecha_full_in, now_str())

        enviado_matriz = 1 if request.form.get("enviado_matriz") == "1" else 0
        destino_otro = (request.form.get("destino_otro", "") or "").strip()

        # ---------- normaliza ----------
        if tipo_mov not in ("ingreso", "egreso"):
            tipo_mov = "ingreso"
        if metodo not in ("efectivo", "banco"):
            metodo = "efectivo"

        # Si banco, referencia obligatoria
        if metodo == "banco" and not referencia:
            flash("En pagos por banco, ingrese el número de comprobante (referencia).")
            return redirect(url_for("caja_mov_nuevo"))

        # ---------- leer items (venta) ----------
        # Soportamos varios nombres por si tu HTML cambia:
        prod_ids = request.form.getlist("producto_id[]") or request.form.getlist("producto_id")
        qtys = request.form.getlist("cantidad_item[]") or request.form.getlist("cantidad_item") or request.form.getlist("cantidad[]")

        items = []
        if prod_ids and qtys and len(prod_ids) == len(qtys):
            for pid_raw, q_raw in zip(prod_ids, qtys):
                pid_raw = (pid_raw or "").strip()
                q_raw = (q_raw or "").strip()
                if not pid_raw or not q_raw:
                    continue
                try:
                    pid = int(pid_raw)
                    # cantidad puede ser int o decimal (por eso float)
                    qty = float(q_raw.replace(",", "."))
                    if qty <= 0:
                        continue
                    items.append((pid, qty))
                except Exception:
                    continue

        # ---------- validar monto ----------
        # Si hay items y el usuario no puso monto, permitimos 0 (para que luego lo sumes manual).
        # Pero SI tú quieres obligatorio, ponlo required en HTML.
        try:
            monto = float(monto_raw.replace(",", ".")) if monto_raw else 0.0
            if monto < 0:
                raise ValueError()
        except ValueError:
            flash("Monto inválido.")
            return redirect(url_for("caja_mov_nuevo"))

        # Regla: Si tipo_mov = ingreso y hay items, interpretamos como "VENTA":
        # - Caja: ingreso (suma si efectivo, o registra banco)
        # - Inventario: egreso (descuenta stock)
        is_venta = (tipo_mov == "ingreso" and len(items) > 0)

        conn = db_conn()
        try:
            cur = conn.cursor()
            cur.execute("BEGIN;")

            ensure_caja_estado(cur, fecha_dia)

            # 1) Insertar movimiento caja
            mov_id = insert_caja_movimiento(cur, {
                "fecha": fecha_full,         # compat
                "fecha_full": fecha_full,    # nuevo
                "dia": fecha_dia,
                "monto": monto,
                "motivo": motivo,
                "referencia": referencia,
                "tipo_mov": tipo_mov,
                "metodo": metodo,
                "enviado_matriz": enviado_matriz,
                "destino_otro": destino_otro if tipo_mov == "egreso" else None,
            })

            # 2) Si es venta: guardar items + descontar stock + registrar movimientos de inventario
            if is_venta:
                # Validar tabla items existe
                if not table_exists(cur, "caja_mov_items"):
                    raise RuntimeError("No existe la tabla caja_mov_items. Ejecuta primero: python db.py")

                # Validar productos + stock suficiente
                # (bloqueo lógico: SQLite no tiene FOR UPDATE real, pero en transacción funciona bien)
                for pid, qty in items:
                    cur.execute("""
                        SELECT id, sku, nombre, stock_actual, activo
                        FROM productos
                        WHERE id=? AND activo=1
                    """, (pid,))
                    p = cur.fetchone()
                    if not p:
                        raise ValueError(f"Producto inválido o inactivo (id={pid}).")

                    stock = float(p["stock_actual"] or 0)
                    if qty > stock:
                        raise ValueError(f"Stock insuficiente para {p['nombre']} ({p['sku']}). Disponible: {stock}, solicitado: {qty}")

                # Aplicar
                for pid, qty in items:
                    cur.execute("SELECT sku, nombre FROM productos WHERE id=?", (pid,))
                    p = cur.fetchone()

                    # items por movimiento
                    cur.execute("""
                        INSERT INTO caja_mov_items (movimiento_id, producto_id, sku, nombre, cantidad)
                        VALUES (?, ?, ?, ?, ?)
                    """, (mov_id, pid, p["sku"], p["nombre"], qty))

                    # descontar stock
                    cur.execute("""
                        UPDATE productos
                        SET stock_actual = stock_actual - ?
                        WHERE id=? AND activo=1
                    """, (qty, pid))

                    # registrar movimiento inventario (egreso)
                    mov_motivo = motivo if motivo else f"Venta (caja_mov_id={mov_id})"
                    cur.execute("""
                        INSERT INTO movimientos (producto_id, tipo_mov, cantidad, motivo, fecha)
                        VALUES (?, 'egreso', ?, ?, ?)
                    """, (pid, int(qty) if qty.is_integer() else int(round(qty)), mov_motivo, fecha_full))

            # 3) Si es egreso: (solo caja) ya quedó registrado.
            #    Si quieres que "enviado_matriz" obligue efectivo, eso se valida en front,
            #    pero aquí lo dejamos libre.

            conn.commit()
            if is_venta:
                flash("✅ Venta registrada: caja + descuento de stock.")
            else:
                flash("Movimiento registrado ✅")
            return redirect(url_for("caja_home"))

        except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
            conn.rollback()
            flash(f"Error de base de datos: {e}")
            return redirect(url_for("caja_mov_nuevo"))

        except ValueError as e:
            conn.rollback()
            flash(str(e))
            return redirect(url_for("caja_mov_nuevo"))

        except Exception as e:
            conn.rollback()
            flash(f"Error inesperado: {e}")
            return redirect(url_for("caja_mov_nuevo"))

        finally:
            conn.close()

    # GET
    return render_template("caja_mov_form.html", modo="mov", dia=dia_default, estado=None, page_class="page-wide")

@app.route("/venta/nueva")
@login_required
def venta_nueva():
    # Abre el formulario de movimiento ya en modo "venta"
    return redirect(url_for("caja_mov_nuevo", preset="venta"))

# -------------------------
# HISTORIAL (por rango) + soporte para calendario (API)
# -------------------------
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

    medio_col = caja_col_medio(cur)
    fecha_expr = caja_fecha_expr(cur)

    params = [start, end]
    where_extra = ""

    if metodo in ("efectivo", "banco"):
        where_extra = f" AND {medio_col}=? "
        params.append(metodo)

    cur.execute(f"""
        SELECT *
        FROM caja_movimientos
        WHERE date({fecha_expr}) BETWEEN ? AND ?
        {where_extra}
        ORDER BY datetime({fecha_expr}) DESC, id DESC
    """, tuple(params))
    rows = cur.fetchall()

    cur.execute(f"""
        SELECT
          COALESCE(SUM(CASE WHEN tipo_mov='ingreso' THEN monto ELSE 0 END),0) AS ing,
          COALESCE(SUM(CASE WHEN tipo_mov='egreso' THEN monto ELSE 0 END),0) AS egr
        FROM caja_movimientos
        WHERE date({fecha_expr}) BETWEEN ? AND ?
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


@app.route("/api/caja/movimientos")
@login_required
def api_caja_movimientos_por_dia():
    """
    Para calendario:
      /api/caja/movimientos?dia=YYYY-MM-DD
    Retorna lista de movimientos del día.
    """
    dia = (request.args.get("dia", "") or "").strip()
    dia = parse_date_yyyy_mm_dd(dia, today_str())

    conn = db_conn()
    cur = conn.cursor()

    fecha_expr = caja_fecha_expr(cur)

    cur.execute(f"""
        SELECT id, dia, monto, motivo, referencia, tipo_mov,
               COALESCE(metodo, medio) AS metodo,
               enviado_matriz, destino_otro,
               COALESCE(fecha_full, fecha) AS fecha
        FROM caja_movimientos
        WHERE dia=?
        ORDER BY datetime({fecha_expr}) DESC, id DESC
    """, (dia,))
    rows = cur.fetchall()
    conn.close()

    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "dia": r["dia"] or "",
            "fecha": r["fecha"] or "",
            "tipo_mov": r["tipo_mov"] or "",
            "metodo": r["metodo"] or "",
            "monto": float(r["monto"] or 0),
            "motivo": r["motivo"] or "",
            "referencia": r["referencia"] or "",
            "enviado_matriz": int(r["enviado_matriz"] or 0),
            "destino_otro": r["destino_otro"] or "",
        })
    return jsonify(out)


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
    if "username" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        correo = request.form.get("email", "").strip()
        if not correo:
            flash("Ingrese su correo para recuperar la contraseña.")
            return redirect(url_for("forgot_password"))

        flash("✅ Solicitud enviada. MIKEN se contactará desde miken.heladeria@gmail.com.")
        return redirect(url_for("login"))

    return render_template("forgot_password.html", hide_nav=True, page_class="page-login", title="MIKEN - Recuperar contraseña")


# --------------------
# MAIN
# --------------------
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
