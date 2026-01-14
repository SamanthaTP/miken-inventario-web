import sqlite3

DB_NAME = "miken.db"


def db_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    # IMPORTANTE: habilita FK en SQLite (por conexión)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return column in [r[1] for r in cur.fetchall()]


def add_column_if_missing(cur, table: str, column: str, ddl: str):
    """
    SQLite: ALTER TABLE ADD COLUMN NO permite DEFAULT con expresiones:
    (date('now')) o (datetime('now')).
    Por eso aquí solo se agregan columnas sin defaults expresivos.
    """
    if not column_exists(cur, table, column):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        print(f"✅ Columna agregada: {table}.{column}")


def ensure_indexes(cur):
    # Índices recomendados
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

        # NOTA: en ALTER no ponemos datetime('now'); luego hacemos backfill
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

        # Si la tabla ya existía sin columnas, migramos sin meter producto_id=0
        # (mejor NULL temporalmente que 0 inválido)
        add_column_if_missing(cur, "movimientos", "producto_id", "producto_id INTEGER")
        add_column_if_missing(cur, "movimientos", "tipo_mov", "tipo_mov TEXT")
        add_column_if_missing(cur, "movimientos", "cantidad", "cantidad INTEGER")
        add_column_if_missing(cur, "movimientos", "motivo", "motivo TEXT")
        add_column_if_missing(cur, "movimientos", "fecha", "fecha TEXT")

        # -------------------------
        # CAJA
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
            enviado_matriz INTEGER NOT NULL DEFAULT 0 CHECK (enviado_matriz IN (0,1))
        )
        """)
        add_column_if_missing(cur, "caja_movimientos", "fecha", "fecha TEXT")
        add_column_if_missing(cur, "caja_movimientos", "dia", "dia TEXT")
        add_column_if_missing(cur, "caja_movimientos", "monto", "monto REAL NOT NULL DEFAULT 0")
        add_column_if_missing(cur, "caja_movimientos", "motivo", "motivo TEXT")
        add_column_if_missing(cur, "caja_movimientos", "referencia", "referencia TEXT")
        add_column_if_missing(cur, "caja_movimientos", "tipo_mov", "tipo_mov TEXT")
        add_column_if_missing(cur, "caja_movimientos", "metodo", "metodo TEXT")
        add_column_if_missing(cur, "caja_movimientos", "enviado_matriz", "enviado_matriz INTEGER NOT NULL DEFAULT 0")

        # Backfill de fechas vacías por ALTER sin DEFAULT expresivo
        backfill_timestamps(cur)

        # Índices
        ensure_indexes(cur)

        cur.execute("COMMIT;")
        print("✅ Migración completa (productos, movimientos, caja) con FK + checks + backfill + índices.")

    except Exception as e:
        cur.execute("ROLLBACK;")
        raise e

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
