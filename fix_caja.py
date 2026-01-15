import sqlite3

DB_NAME = "miken.db"

def main():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # 1) Ver registro conflictivo (para confirmar)
    try:
        cur.execute("SELECT id, tipo_mov, metodo, enviado_matriz, dia, fecha FROM caja_movimientos WHERE id=1")
        print("ID=1:", cur.fetchone())
    except Exception as e:
        print("No pude leer caja_movimientos:", e)

    # 2) Normalizar tipo_mov
    cur.execute("""
        UPDATE caja_movimientos
        SET tipo_mov = lower(trim(tipo_mov))
        WHERE tipo_mov IS NOT NULL
    """)

    # Mapear valores comunes incorrectos
    cur.execute("""
        UPDATE caja_movimientos
        SET tipo_mov = 'ingreso'
        WHERE tipo_mov NOT IN ('ingreso','egreso') OR tipo_mov IS NULL OR trim(tipo_mov)=''
    """)

    # 3) Normalizar metodo
    cur.execute("""
        UPDATE caja_movimientos
        SET metodo = lower(trim(metodo))
        WHERE metodo IS NOT NULL
    """)

    cur.execute("""
        UPDATE caja_movimientos
        SET metodo = 'efectivo'
        WHERE metodo NOT IN ('efectivo','banco') OR metodo IS NULL OR trim(metodo)=''
    """)

    # 4) Normalizar enviado_matriz
    # si hay valores raros, los bajamos a 0/1
    cur.execute("""
        UPDATE caja_movimientos
        SET enviado_matriz =
          CASE
            WHEN enviado_matriz IN (1, '1', 'true', 'True', 'TRUE') THEN 1
            ELSE 0
          END
        WHERE enviado_matriz IS NOT NULL
    """)
    cur.execute("""
        UPDATE caja_movimientos
        SET enviado_matriz = 0
        WHERE enviado_matriz IS NULL
    """)

    # 5) Asegurar dia (si está vacío lo calculamos desde fecha)
    cur.execute("""
        UPDATE caja_movimientos
        SET dia = date(fecha)
        WHERE (dia IS NULL OR trim(dia)='') AND fecha IS NOT NULL AND trim(fecha)!=''
    """)

    conn.commit()

    # Mostrar id=1 después del fix
    cur.execute("SELECT id, tipo_mov, metodo, enviado_matriz, dia, fecha FROM caja_movimientos WHERE id=1")
    print("ID=1 (FIXED):", cur.fetchone())

    conn.close()
    print("✅ Caja reparada: valores normalizados y CHECK ya no debe fallar.")

if __name__ == "__main__":
    main()

