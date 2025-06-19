import sqlite3
import json

def limpiar_historial_jugadores():
    conn = sqlite3.connect("jugadores.db")  # Cambiá por el nombre correcto de tu DB
    cursor = conn.cursor()

    cursor.execute("SELECT id, historial FROM jugadores")
    jugadores = cursor.fetchall()

    jugadores_actualizados = 0

    for jugador_id, historial_json in jugadores:
        if not historial_json:
            continue

        try:
            historial = json.loads(historial_json)
            historial_sin_duplicados = [dict(t) for t in {tuple(sorted(d.items())) for d in historial}]

            if len(historial_sin_duplicados) != len(historial):
                nuevo_json = json.dumps(historial_sin_duplicados, ensure_ascii=False)
                cursor.execute("UPDATE jugadores SET historial = ? WHERE id = ?", (nuevo_json, jugador_id))
                jugadores_actualizados += 1
        except Exception as e:
            print(f"Error en jugador ID {jugador_id}: {e}")

    conn.commit()
    conn.close()

    print(f"✅ Historial limpiado para {jugadores_actualizados} jugadores.")

# Ejecutar
limpiar_historial_jugadores()
