import json

archivo = 'jugadores.json'

# Cargar los jugadores
with open(archivo, 'r', encoding='utf-8') as f:
    jugadores = json.load(f)

# Filtrar: solo jugadores con nombre no vacío
jugadores_limpios = [j for j in jugadores if j.get('nombre', '').strip() != '']

# Sobrescribir el archivo
with open(archivo, 'w', encoding='utf-8') as f:
    json.dump(jugadores_limpios, f, indent=4)

print("Jugadores sin nombre eliminados correctamente.")
