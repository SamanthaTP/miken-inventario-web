import sqlite3

DB_NAME = "miken.db"


def db_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return column in [r[1] for r in cur.fetchall()]


def add_column_if_missing(cur, table: str, column: str, ddl: str):
    """
    SQLite: ALTER TABLE ADD COLUMN NO permite DEFAULT con expresiones (date('now'), datetime('now')).
    Por eso si agregamos columnas por ALTER, las agregamos sin defaults expresivos y luego backfill.
    """
    if not column_exists(cur, table, column):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        print(f"✅ Columna agregada: {table}.{column}")


def ensure_indexes(cur):
    cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_producto_id ON movimientos(producto_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_fecha ON movimientos(fecha)")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_caja_mov_dia ON caja_movimientos(dia)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_caja_mov_fecha ON caja_movimientos(fecha)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_caja_estado_dia ON caja_estado(dia)")


def backfill_timestamps(cur):
    # Rellenar timestamps vacíos si existen
    for table, col in [
        ("productos", "created_at"),
        ("movimientos", "fecha"),
        ("caja_estado", "created_at"),
        ("caja_aperturas", "fecha"),
        ("caja_cierres", "fecha"),
        ("caja_movimientos", "fecha"),
    ]:
        if column_exists(cur, table, col):
            cur.execute(
                f"""
                UPDATE {table}
                SET {col} = datetime('now')
                WHERE {col} IS NULL OR TRIM({col}) = ''
                """
            )


def normalize_caja_movimientos(cur):
    """
    Evita errores por CHECK:
      - tipo_mov debe ser 'ingreso' o 'egreso'
      - metodo debe ser 'efectivo' o 'banco'
      - enviado_matriz debe ser 0 o 1
    Además, soporta compatibilidad: si existe 'medio'/'tipo', los alinea con 'metodo'/'tipo_mov'.
    """
    # Asegura valores válidos donde existan columnas
    if column_exists(cur, "caja_movimientos", "tipo_mov"):
        cur.execute("""
            UPDATE caja_movimientos
            SET tipo_mov = 'ingreso'
            WHERE tipo_mov IS NULL OR TRIM(tipo_mov) = '' OR tipo_mov NOT IN ('ingreso','egreso')
        """)

    if column_exists(cur, "caja_movimientos", "metodo"):
        cur.execute("""
            UPDATE caja_movimientos
            SET metodo = 'efectivo'
            WHERE metodo IS NULL OR TRIM(metodo) = '' OR metodo NOT IN ('efectivo','banco')
        """)

    if column_exists(cur, "caja_movimientos", "enviado_matriz"):
        cur.execute("""
            UPDATE caja_movimientos
            SET enviado_matriz = 0
            WHERE enviado_matriz IS NULL OR enviado_matriz NOT IN (0,1)
        """)

    # Compatibilidad: 'medio' <-> 'metodo'
    has_medio = column_exists(cur, "caja_movimientos", "medio")
    has_metodo = column_exists(cur, "caja_movimientos", "metodo")
    if has_medio and has_metodo:
        # Si metodo vacío, toma medio; si medio vacío, toma metodo
        cur.execute("""
            UPDATE caja_movimientos
            SET metodo = COALESCE(NULLIF(TRIM(metodo), ''), medio)
            WHERE metodo IS NULL OR TRIM(metodo) = ''
        """)
        cur.execute("""
            UPDATE caja_movimientos
            SET medio = COALESCE(NULLIF(TRIM(medio), ''), metodo)
            WHERE medio IS NULL OR TRIM(medio) = ''
        """)
        # Asegura valores válidos
        cur.execute("""
            UPDATE caja_movimientos
            SET medio = 'efectivo'
            WHERE medio IS NULL OR TRIM(medio) = '' OR medio NOT IN ('efectivo','banco')
        """)
        cur.execute("""
            UPDATE caja_movimientos
            SET metodo = 'efectivo'
            WHERE metodo IS NULL OR TRIM(metodo) = '' OR metodo NOT IN ('efectivo','banco')
        """)

    # Compatibilidad: 'tipo' <-> 'tipo_mov'
    has_tipo = column_exists(cur, "caja_movimientos", "tipo")
    has_tipo_mov = column_exists(cur, "caja_movimientos", "tipo_mov")
    if has_tipo and has_tipo_mov:
        cur.execute("""
            UPDATE caja_movimientos
            SET tipo_mov = COALESCE(NULLIF(TRIM(tipo_mov), ''), tipo)
            WHERE tipo_mov IS NULL OR TRIM(tipo_mov) = ''
        """)
        cur.execute("""
            UPDATE caja_movimientos
            SET tipo = COALESCE(NULLIF(TRIM(tipo), ''), tipo_mov)
            WHERE tipo IS NULL OR TRIM(tipo) = ''
        """)
        cur.execute("""
            UPDATE caja_movimientos
            SET tipo = 'ingreso'
            WHERE tipo IS NULL OR TRIM(tipo) = '' OR tipo NOT IN ('ingreso','egreso')
        """)
        cur.execute("""
            UPDATE caja_movimientos
            SET tipo_mov = 'ingreso'
            WHERE tipo_mov IS NULL OR TRIM(tipo_mov) = '' OR tipo_mov NOT IN ('ingreso','egreso')
        """)


def migrate():
    conn = db_conn()
    cur = conn.cursor()

    try:
        cur.execute("BEGIN;")

        # -------------------------
        # PRODUCTOS
        # -------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL DEFAULT 'insumo',
            sku TEXT,
            nombre TEXT NOT NULL,
            categoria TEXT,
            unidad TEXT,
            precio REAL NOT NULL DEFAULT 0,
            stock_actual INTEGER NOT NULL DEFAULT 0,
            stock_min INTEGER NOT NULL DEFAULT 0,
            imagen_filename TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """)

        add_column_if_missing(cur, "productos", "tipo", "tipo TEXT")
        add_column_if_missing(cur, "productos", "sku", "sku TEXT")
        add_column_if_missing(cur, "productos", "categoria", "categoria TEXT")
        add_column_if_missing(cur, "productos", "unidad", "unidad TEXT")
        add_column_if_missing(cur, "productos", "precio", "precio REAL NOT NULL DEFAULT 0")
        add_column_if_missing(cur, "productos", "stock_actual", "stock_actual INTEGER NOT NULL DEFAULT 0")
        add_column_if_missing(cur, "productos", "stock_min", "stock_min INTEGER NOT NULL DEFAULT 0")
        add_column_if_missing(cur, "productos", "imagen_filename", "imagen_filename TEXT")
        add_column_if_missing(cur, "productos", "activo", "activo INTEGER NOT NULL DEFAULT 1")
        add_column_if_missing(cur, "productos", "created_at", "created_at TEXT")

        # -------------------------
        # MOVIMIENTOS INVENTARIO
        # -------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            tipo_mov TEXT NOT NULL CHECK (tipo_mov IN ('ingreso','egreso')),
            cantidad INTEGER NOT NULL CHECK (cantidad > 0),
            motivo TEXT,
            fecha TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (producto_id) REFERENCES productos(id) ON UPDATE CASCADE ON DELETE RESTRICT
        )
        """)

        add_column_if_missing(cur, "movimientos", "producto_id", "producto_id INTEGER")
        add_column_if_missing(cur, "movimientos", "tipo_mov", "tipo_mov TEXT")
        add_column_if_missing(cur, "movimientos", "cantidad", "cantidad INTEGER")
        add_column_if_missing(cur, "movimientos", "motivo", "motivo TEXT")
        add_column_if_missing(cur, "movimientos", "fecha", "fecha TEXT")

        # -------------------------
        # CAJA - ESTADO
        # -------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS caja_estado (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dia TEXT NOT NULL UNIQUE,
            abierta INTEGER NOT NULL DEFAULT 0,
            efectivo_inicial REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """)
        add_column_if_missing(cur, "caja_estado", "dia", "dia TEXT")
        add_column_if_missing(cur, "caja_estado", "abierta", "abierta INTEGER NOT NULL DEFAULT 0")
        add_column_if_missing(cur, "caja_estado", "efectivo_inicial", "efectivo_inicial REAL NOT NULL DEFAULT 0")
        add_column_if_missing(cur, "caja_estado", "created_at", "created_at TEXT")

        # -------------------------
        # CAJA - APERTURAS
        # -------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS caja_aperturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dia TEXT NOT NULL,
            efectivo_inicial REAL NOT NULL DEFAULT 0,
            nota TEXT,
            fecha TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """)
        add_column_if_missing(cur, "caja_aperturas", "dia", "dia TEXT")
        add_column_if_missing(cur, "caja_aperturas", "efectivo_inicial", "efectivo_inicial REAL NOT NULL DEFAULT 0")
        add_column_if_missing(cur, "caja_aperturas", "nota", "nota TEXT")
        add_column_if_missing(cur, "caja_aperturas", "fecha", "fecha TEXT")

        # -------------------------
        # CAJA - CIERRES
        # -------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS caja_cierres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dia TEXT NOT NULL,
            efectivo_final REAL NOT NULL DEFAULT 0,
            total_ingresos REAL NOT NULL DEFAULT 0,
            total_egresos REAL NOT NULL DEFAULT 0,
            nota TEXT,
            fecha TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """)
        add_column_if_missing(cur, "caja_cierres", "dia", "dia TEXT")
        add_column_if_missing(cur, "caja_cierres", "efectivo_final", "efectivo_final REAL NOT NULL DEFAULT 0")
        add_column_if_missing(cur, "caja_cierres", "total_ingresos", "total_ingresos REAL NOT NULL DEFAULT 0")
        add_column_if_missing(cur, "caja_cierres", "total_egresos", "total_egresos REAL NOT NULL DEFAULT 0")
        add_column_if_missing(cur, "caja_cierres", "nota", "nota TEXT")
        add_column_if_missing(cur, "caja_cierres", "fecha", "fecha TEXT")

        # -------------------------
        # CAJA - MOVIMIENTOS
        # -------------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS caja_movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL DEFAULT (datetime('now')),
            dia TEXT,
            monto REAL NOT NULL DEFAULT 0,
            motivo TEXT,
            referencia TEXT,
            tipo_mov TEXT NOT NULL DEFAULT 'ingreso' CHECK (tipo_mov IN ('ingreso','egreso')),
            metodo TEXT NOT NULL DEFAULT 'efectivo' CHECK (metodo IN ('efectivo','banco')),
            enviado_matriz INTEGER NOT NULL DEFAULT 0 CHECK (enviado_matriz IN (0,1)),
            -- Campos opcionales para banco (si luego los usas)
            comprobante TEXT,
            banco_nombre TEXT,
            -- Compatibilidad por si tu app aún usa estos nombres:
            medio TEXT,
            tipo TEXT
        )
        """)

        # Columnas principales
        add_column_if_missing(cur, "caja_movimientos", "fecha", "fecha TEXT")
        add_column_if_missing(cur, "caja_movimientos", "dia", "dia TEXT")
        add_column_if_missing(cur, "caja_movimientos", "monto", "monto REAL NOT NULL DEFAULT 0")
        add_column_if_missing(cur, "caja_movimientos", "motivo", "motivo TEXT")
        add_column_if_missing(cur, "caja_movimientos", "referencia", "referencia TEXT")
        add_column_if_missing(cur, "caja_movimientos", "tipo_mov", "tipo_mov TEXT")
        add_column_if_missing(cur, "caja_movimientos", "metodo", "metodo TEXT")
        add_column_if_missing(cur, "caja_movimientos", "enviado_matriz", "enviado_matriz INTEGER NOT NULL DEFAULT 0")

        # Para banco (si tu HTML/app los pide)
        add_column_if_missing(cur, "caja_movimientos", "comprobante", "comprobante TEXT")
        add_column_if_missing(cur, "caja_movimientos", "banco_nombre", "banco_nombre TEXT")

        # Compatibilidad con código viejo que use "medio" o "tipo"
        add_column_if_missing(cur, "caja_movimientos", "medio", "medio TEXT")
        add_column_if_missing(cur, "caja_movimientos", "tipo", "tipo TEXT")

        # Backfill fechas vacías
        backfill_timestamps(cur)

        # Normaliza para no chocar con CHECK en runtime
        normalize_caja_movimientos(cur)

        # Índices
        ensure_indexes(cur)

        cur.execute("COMMIT;")
        print("✅ Migración completa (productos, movimientos, caja) con normalización y compatibilidad.")

    except Exception:
        cur.execute("ROLLBACK;")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
