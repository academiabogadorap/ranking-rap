import json

# --- Rutas de archivos ---
archivo_resultados = 'resultados.json'
archivo_ranking = 'ranking.json'

# --- Convertir resultados.json a diccionario ---
with open(archivo_resultados, 'r', encoding='utf-8') as f:
    resultados_lista = json.load(f)

resultados_dict = {}
for jugador in resultados_lista:
    nombre = jugador.get('nombre', '').strip().upper()
    resultados_dict[nombre] = {
        'torneos': jugador.get('torneos', [])
    }

with open('resultados_convertido.json', 'w', encoding='utf-8') as f:
    json.dump(resultados_dict, f, ensure_ascii=False, indent=2)

print("✅ resultados.json convertido correctamente a resultados_convertido.json")


# --- Convertir ranking.json a lista de dicts ---
with open(archivo_ranking, 'r', encoding='utf-8') as f:
    ranking_lista_cruda = json.load(f)

ranking_procesado = []
for linea in ranking_lista_cruda:
    if "Nombre:" in linea and "Puntos:" in linea:
        partes = linea.split("-")
        nombre = partes[0].replace("Nombre:", "").strip()
        puntos = int(partes[1].replace("Puntos:", "").strip())
        ranking_procesado.append({
            "nombre": nombre,
            "puntos": puntos
        })

with open('ranking_convertido.json', 'w', encoding='utf-8') as f:
    json.dump(ranking_procesado, f, ensure_ascii=False, indent=2)

print("✅ ranking.json convertido correctamente a ranking_convertido.json")
