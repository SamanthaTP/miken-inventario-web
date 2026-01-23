import sqlite3

DB_NAME = "miken.db"

conn = sqlite3.connect(DB_NAME)
cur = conn.cursor()


cur.execute("PRAGMA table_info(caja_movimientos)")
cols = [r[1] for r in cur.fetchall()]
print("Columnas caja_movimientos:", cols)

print("TABLAS:")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for (name,) in cur.fetchall():
    print(" -", name)

print("\nCOLUMNAS de caja_movimientos (si existe):")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='caja_movimientos'")
exists = cur.fetchone()

if not exists:
    print("❌ No existe la tabla caja_movimientos")
else:
    cur.execute("PRAGMA table_info(caja_movimientos)")
    for row in cur.fetchall():
        # row = (cid, name, type, notnull, dflt_value, pk)
        print(f" - {row[1]} ({row[2]}) default={row[4]}")



conn.close()
