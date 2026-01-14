import sqlite3

DB_NAME = "miken.db"

def table_exists(cur, table):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None

def column_exists(cur, table, col):
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    return col in cols

def migrate_caja():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # 1) Detectar tabla de movimientos de caja (por nombre típico)
    candidatos = ["caja_movimientos", "caja_mov", "caja_chica_movimientos", "movimientos_caja", "caja_chica_mov"]
    tabla = None
    for t in candidatos:
        if table_exists(cur, t):
            tabla = t
            break

    if not tabla:
        # Si no existe, la creamos con el esquema mínimo (ajústalo luego si ya tienes otro)
        tabla = "caja_movimientos"
        cur.execute("""
        CREATE TABLE IF NOT EXISTS caja_movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_mov TEXT NOT NULL DEFAULT 'ingreso',   -- ingreso / egreso
            monto REAL NOT NULL DEFAULT 0,
            metodo TEXT NOT NULL DEFAULT 'efectivo',    -- efectivo / banco
            comprobante TEXT,
            motivo TEXT,
            fecha TEXT NOT NULL DEFAULT (date('now'))
        )
        """)

    # 2) Asegurar columnas necesarias
    if not column_exists(cur, tabla, "tipo_mov"):
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN tipo_mov TEXT NOT NULL DEFAULT 'ingreso'")

    if not column_exists(cur, tabla, "monto"):
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN monto REAL NOT NULL DEFAULT 0")

    if not column_exists(cur, tabla, "metodo"):
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN metodo TEXT NOT NULL DEFAULT 'efectivo'")

    if not column_exists(cur, tabla, "comprobante"):
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN comprobante TEXT")

    if not column_exists(cur, tabla, "motivo"):
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN motivo TEXT")

    if not column_exists(cur, tabla, "fecha"):
        cur.execute(f"ALTER TABLE {tabla} ADD COLUMN fecha TEXT NOT NULL DEFAULT (date('now'))")

    conn.commit()
    conn.close()
    print(f"✅ Migración OK. Tabla usada: {tabla}")

if __name__ == "__main__":
    migrate_caja()
