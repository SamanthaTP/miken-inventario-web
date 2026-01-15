import sqlite3

DB = "miken.db"

def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Normalizar tipo_mov y metodo a minúsculas y sin espacios
    cur.execute("""
        UPDATE caja_movimientos
        SET tipo_mov = lower(trim(tipo_mov))
        WHERE tipo_mov IS NOT NULL
    """)
    cur.execute("""
        UPDATE caja_movimientos
        SET metodo = lower(trim(metodo))
        WHERE metodo IS NOT NULL
    """)

    # Corregir tipo_mov inválidos -> ingreso
    cur.execute("""
        UPDATE caja_movimientos
        SET tipo_mov = 'ingreso'
        WHERE tipo_mov IS NULL OR trim(tipo_mov)='' OR tipo_mov NOT IN ('ingreso','egreso')
    """)

    # Corregir metodo inválidos -> efectivo
    cur.execute("""
        UPDATE caja_movimientos
        SET metodo = 'efectivo'
        WHERE metodo IS NULL OR trim(metodo)='' OR metodo NOT IN ('efectivo','banco')
    """)

    # Corregir enviado_matriz inválidos -> 0/1
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
        WHERE enviado_matriz IS NULL OR enviado_matriz NOT IN (0,1)
    """)

    # Corregir dia vacío (si fecha existe)
    cur.execute("""
        UPDATE caja_movimientos
        SET dia = date(fecha)
        WHERE (dia IS NULL OR trim(dia)='') AND fecha IS NOT NULL AND trim(fecha)!=''
    """)

    con.commit()

    # Mostrar id=1 luego del fix
    cur.execute("SELECT id, tipo_mov, metodo, enviado_matriz, dia, fecha FROM caja_movimientos WHERE id=1")
    r = cur.fetchone()
    print("ID=1 FIXED:", dict(r) if r else "No existe id=1")

    con.close()
    print("✅ Fix aplicado. Reintenta Caja.")
    
if __name__ == "__main__":
    main()
