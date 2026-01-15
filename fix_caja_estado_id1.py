import sqlite3
from datetime import date, datetime

DB = "miken.db"

def today_str():
    return date.today().isoformat()

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Normaliza el registro id=1 si existe
    cur.execute("SELECT * FROM caja_estado WHERE id=1")
    r = cur.fetchone()
    if not r:
        print("No existe caja_estado id=1. Nada que corregir.")
        con.close()
        return

    dia = r["dia"] if r["dia"] else today_str()
    # Fuerza formato correcto de día
    try:
        datetime.strptime(dia, "%Y-%m-%d")
    except:
        dia = today_str()

    # Asegura tipos válidos para CHECK típicos
    abierta = 1 if str(r["abierta"]) in ("1", "True", "true") else 0
    try:
        efectivo_inicial = float(r["efectivo_inicial"] or 0)
    except:
        efectivo_inicial = 0.0

    cur.execute("""
        UPDATE caja_estado
        SET dia=?, abierta=?, efectivo_inicial=?, created_at=COALESCE(created_at, ?)
        WHERE id=1
    """, (dia, abierta, efectivo_inicial, now_str()))

    con.commit()

    cur.execute("SELECT * FROM caja_estado WHERE id=1")
    print("ID=1 FIXED:", dict(cur.fetchone()))
    con.close()
    print("✅ Corrección aplicada.")

if __name__ == "__main__":
    main()
