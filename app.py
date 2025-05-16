from flask import Flask, render_template, request, redirect, url_for, session
from collections import defaultdict
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'clave_super_secreta'

# Datos en memoria (reemplazable por BD)
jugadores = []  # [{"nombre": "Juan Pérez", "categoria": "7ma", "puntos": 0}]
niveles = {
    "A": 1000,
    "B": 600,
    "C": 300,
    "D": 150
}
mult_puntos = {
    "Campeon": 1.0,
    "Finalista": 0.6,
    "Semifinalista": 0.36,
    "Cuartos": 0.18,
    "Octavos": 0.09,
    "Primera ronda": 0.0
}

def calcular_ranking_temporada(jugadores, cantidad_maxima=10):
    ranking = []
    anio_actual = datetime.today().year

    for jugador in jugadores:
        historial = jugador.get("historial", [])

        # Filtrar torneos del año actual
        anuales = [
            h for h in historial
            if datetime.strptime(h["fecha"], "%Y-%m-%d").year == anio_actual
        ]

        # Ordenar por puntos y tomar los mejores
        mejores = sorted(anuales, key=lambda x: x["puntos"], reverse=True)[:cantidad_maxima]
        total = sum(h["puntos"] for h in mejores)
        mejor_torneo = mejores[0]["puntos"] if mejores else 0

        ranking.append({
            "nombre": jugador["nombre"],
            "categoria": jugador["categoria"],
            "puntos": total,
            "torneos_contados": len(mejores),
            "mejor_torneo": mejor_torneo
        })

    # Ordenar el ranking con criterios de desempate
    ranking_ordenado = sorted(
        ranking,
        key=lambda x: (
            -x["puntos"],            # 1️⃣ Más puntos
            -x["torneos_contados"], # 2️⃣ Más torneos válidos
            -x["mejor_torneo"],     # 3️⃣ Mayor puntaje en un solo torneo
            x["nombre"]             # 4️⃣ Orden alfabético (último recurso)
        )
    )

    return ranking_ordenado


@app.route('/')
def index():
    categoria_filtrada = request.args.get('categoria', default=None)
    provincia_filtrada = request.args.get('provincia', default=None)
    localidad_filtrada = request.args.get('localidad', default=None)

    # Filtrar por categoría, provincia y localidad
    jugadores_filtrados = jugadores
    if categoria_filtrada:
        jugadores_filtrados = [j for j in jugadores_filtrados if j['categoria'] == categoria_filtrada]
    if provincia_filtrada:
        jugadores_filtrados = [j for j in jugadores_filtrados if j.get('provincia', '').lower() == provincia_filtrada.lower()]
    if localidad_filtrada:
        jugadores_filtrados = [j for j in jugadores_filtrados if j.get('localidad', '').lower() == localidad_filtrada.lower()]

    # Ranking con los mejores 6 torneos
    ranking = calcular_ranking_temporada(jugadores_filtrados, cantidad_maxima=6)

    # Añadir localidad y provincia al resultado
    for r in ranking:
        original = next((j for j in jugadores if j['nombre'] == r['nombre']), {})
        r['localidad'] = original.get('localidad', '–')
        r['provincia'] = original.get('provincia', '–')

    # Filtros disponibles
    categorias_disponibles = sorted(set(j['categoria'] for j in jugadores if j.get('categoria')))
    provincias_disponibles = sorted(set(j.get('provincia') for j in jugadores if j.get('provincia')))
    localidades_disponibles = sorted(set(j.get('localidad') for j in jugadores if j.get('localidad')))

    return render_template(
        'index.html',
        jugadores=ranking,
        categorias=categorias_disponibles,
        provincias=provincias_disponibles,
        localidades=localidades_disponibles,
        categoria_actual=categoria_filtrada,
        provincia_actual=provincia_filtrada,
        localidad_actual=localidad_filtrada
    )


@app.route('/agregar_jugador', methods=['POST'])
def agregar_jugador():
    nombre = request.form['nombre'].strip().upper()
    categoria = request.form['categoria'].strip()
    jugadores.append({"nombre": nombre, "categoria": categoria, "puntos": 0})
    guardar_jugadores_en_json()
    return redirect(url_for('index'))

@app.route('/editar_jugador/<nombre>')
def editar_jugador(nombre):
    jugador = next((j for j in jugadores if j['nombre'] == nombre), None)
    return render_template('editar_jugador.html', jugador=jugador)

@app.route('/guardar_edicion_jugador', methods=['POST'])
def guardar_edicion_jugador():
    nombre_original = request.form['nombre_original']
    nuevo_nombre = request.form['nombre'].strip().upper()
    nueva_categoria = request.form['categoria'].strip()
    nueva_localidad = request.form.get('localidad', '').strip()
    nueva_provincia = request.form.get('provincia', '').strip()

    for j in jugadores:
        if j['nombre'] == nombre_original:
            j['nombre'] = nuevo_nombre
            j['categoria'] = nueva_categoria
            j['localidad'] = nueva_localidad
            j['provincia'] = nueva_provincia
            break

    guardar_jugadores_en_json()
    return redirect(url_for('index'))


@app.route('/importar_resultado_externo', methods=['GET'])
def mostrar_importar_resultado():
    return render_template('importar_resultado.html', jugadores=jugadores)

@app.route('/importar_resultado_externo_mejorado', methods=['POST'])
def importar_resultado_externo_mejorado():
    torneo = request.form['torneo'].strip()
    fecha = request.form['fecha'].strip()
    nivel = request.form['nivel'].strip().upper()
    categoria_torneo = request.form['categoria_torneo'].strip().upper()
    instancias_form = request.form.getlist('instancia[]')
    jugadores_form = request.form.getlist('jugadores[]')

    for i in range(0, len(jugadores_form), 2):
        jugador1 = jugadores_form[i].strip().upper()
        jugador2 = jugadores_form[i + 1].strip().upper()
        instancia = instancias_form[i // 2].strip()

        # 🔒 Validar si está incompleto (algún jugador vacío)
        if not jugador1 or not jugador2:
            continue

        puntos_base = niveles.get(nivel, 0)
        multiplicador = mult_puntos.get(instancia, 0)
        puntos_totales = puntos_base * multiplicador
        puntos_por_jugador = puntos_totales / 2

        # Validar si alguno tiene categoría superior a la del torneo
        jugador1_data = next((j for j in jugadores if j['nombre'] == jugador1), None)
        jugador2_data = next((j for j in jugadores if j['nombre'] == jugador2), None)

        jugador1_cat = jugador1_data['categoria'].upper() if jugador1_data else "SIN CATEGORIA"
        jugador2_cat = jugador2_data['categoria'].upper() if jugador2_data else "SIN CATEGORIA"

        jugadores_invalidos = []

        if jugador1_cat != "SIN CATEGORIA" and jugador1_cat < categoria_torneo:
            jugadores_invalidos.append(jugador1)
        if jugador2_cat != "SIN CATEGORIA" and jugador2_cat < categoria_torneo:
            jugadores_invalidos.append(jugador2)

        # 🟥 Penalizar a ambos si uno está mal
        if jugadores_invalidos:
            for nombre in [jugador1, jugador2]:
                jugador = next((j for j in jugadores if j['nombre'] == nombre), None)
                if jugador:
                    jugador.setdefault('historial', []).append({
                        'torneo': torneo,
                        'fecha': fecha,
                        'nivel': nivel,
                        'categoria_torneo': categoria_torneo,
                        'pareja': jugador2 if nombre == jugador1 else jugador1,
                        'ronda': instancia,
                        'puntos': 0,
                        'observacion': 'No válido: un jugador estaba en categoría inferior (pareja penalizada)'
                    })
            continue  # se saltea la carga normal para esta pareja

        # ✅ Si no hay jugadores inválidos, continúa como siempre
        for nombre in [jugador1, jugador2]:
            jugador = next((j for j in jugadores if j['nombre'] == nombre), None)

            if not jugador:
                jugador = {
                    'nombre': nombre,
                    'categoria': 'Sin categoría',
                    'puntos': puntos_por_jugador,
                    'historial': [{
                        'torneo': torneo,
                        'fecha': fecha,
                        'nivel': nivel,
                        'categoria_torneo': categoria_torneo,
                        'pareja': jugador2 if nombre == jugador1 else jugador1,
                        'ronda': instancia,
                        'puntos': puntos_por_jugador
                    }]
                }
                jugadores.append(jugador)
            else:
                jugador['puntos'] += puntos_por_jugador
                jugador.setdefault('historial', []).append({
                    'torneo': torneo,
                    'fecha': fecha,
                    'nivel': nivel,
                    'categoria_torneo': categoria_torneo,
                    'pareja': jugador2 if nombre == jugador1 else jugador1,
                    'ronda': instancia,
                    'puntos': puntos_por_jugador
                })

        resultado = {
            "torneo": torneo,
            "fecha": fecha,
            "nivel": nivel,
            "categoria_torneo": categoria_torneo,
            "instancia": instancia,
            "jugadores": [jugador1, jugador2],
            "puntos_totales": puntos_totales,
            "puntos_por_jugador": puntos_por_jugador
        }
        guardar_resultado_en_historial(resultado)

    actualizar_ranking_json(jugadores)
    guardar_jugadores_en_json()
    return redirect(url_for('index'))




@app.route('/eliminar_jugador/<nombre>')
def eliminar_jugador(nombre):
    global jugadores
    jugadores = [j for j in jugadores if j['nombre'] != nombre]
    guardar_jugadores_en_json()
    return redirect(url_for('index'))

@app.route('/historial/<nombre>')
def historial(nombre):
    jugador = next((j for j in jugadores if j['nombre'] == nombre), None)
    historial = jugador.get('historial', []) if jugador else []
    return render_template('historial.html', jugador=jugador, historial=historial)


@app.route('/torneo_academia/<int:id>/generar_cuadro_final', methods=['POST'])
def generar_cuadro_final(id):
    torneo = next((t for t in torneos_academia if t["id"] == id), None)
    if not torneo:
        return redirect(url_for('index'))

    # Calculamos primeros y segundos por zona
    primeros = []
    segundos = []

    for zona in torneo["zonas"]:
        zona_partidos = [p for p in torneo["partidos"] if p["zona"] == zona["nombre"]]
        tabla = calcular_tabla_posiciones(zona, zona_partidos)
        if len(tabla) >= 1:
            primeros.append(tabla[0]["pareja"])
        if len(tabla) >= 2:
            segundos.append(tabla[1]["pareja"])

    # Emparejamiento cruzado: 1° de una zona vs 2° de otra zona
    semifinales = []
    for i in range(min(len(primeros), len(segundos))):
        pareja1 = primeros[i]
        pareja2 = segundos[(i + 1) % len(segundos)]
        semifinales.append({
            "zona": "Cuadro Final",
            "pareja1": pareja1,
            "pareja2": pareja2,
            "ronda": "Semifinal",
            "resultado": None
        })

    # Agregamos la final vacía (espera resultados de semifinales)
    final = {
        "zona": "Cuadro Final",
        "pareja1": ["Ganador", "SF1"],
        "pareja2": ["Ganador", "SF2"],
        "ronda": "Final",
        "resultado": None
    }

    torneo["partidos"].extend(semifinales + [final])
    return redirect(url_for('gestionar_torneo_academia', id=id))

def siguiente_ronda_nombre(ronda):
    orden = ["16avos", "Octavos", "Cuartos", "Semifinal", "Final"]
    if ronda in orden:
        idx = orden.index(ronda)
        return orden[idx + 1] if idx + 1 < len(orden) else "Final"
    return "Eliminación"

def guardar_resultado_en_historial(resultado, archivo='resultados.json'):
    try:
        with open(archivo, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []

    data.append(resultado)

    with open(archivo, 'w') as f:
        json.dump(data, f, indent=4)

def actualizar_ranking_json(jugadores, archivo='ranking.json'):
    ranking = {}
    for j in jugadores:
        ranking[j['nombre']] = j['puntos']
    with open(archivo, 'w') as f:
        json.dump(ranking, f, indent=4)

def guardar_jugadores_en_json(archivo='jugadores.json'):
    with open(archivo, 'w') as f:
        json.dump(jugadores, f, indent=4)

def cargar_jugadores_desde_json(archivo='jugadores.json'):
    global jugadores
    try:
        with open(archivo, 'r') as f:
            jugadores = json.load(f)
    except FileNotFoundError:
        jugadores = []

@app.route('/login_admin', methods=['GET', 'POST'])
def login_admin():
    if request.method == 'POST':
        clave = request.form.get('password')
        if clave == 'clave123':  # 👉 Podés cambiar esta clave por algo más seguro
            session['es_admin'] = True
            return redirect(url_for('index'))
        else:
            return 'Contraseña incorrecta', 403
    return render_template('login_admin.html')


@app.route('/ranking/<categoria>')
def ranking_por_categoria(categoria):
    jugadores_categoria = [j for j in jugadores if j['categoria'] == categoria]

    ranking_base = calcular_ranking_temporada(jugadores_categoria, cantidad_maxima=6)

    # Agregar localidad y provincia al ranking final
    for r in ranking_base:
        jugador_original = next((j for j in jugadores if j['nombre'] == r['nombre']), {})
        r['localidad'] = jugador_original.get('localidad', '–')
        r['provincia'] = jugador_original.get('provincia', '–')

    return render_template('ranking_categoria.html', jugadores=ranking_base, categoria_actual=categoria)


@app.route('/editar_historial/<nombre>/<int:index>', methods=['GET', 'POST'])
def editar_historial(nombre, index):
    jugador = next((j for j in jugadores if j['nombre'] == nombre), None)

    if not jugador or index >= len(jugador.get('historial', [])):
        return redirect(url_for('historial', nombre=nombre))

    if request.method == 'POST':
        # Datos del formulario
        torneo = request.form['torneo'].strip()
        fecha = request.form['fecha'].strip()
        nivel = request.form['nivel'].strip().upper()
        pareja = request.form['pareja'].strip().upper()
        ronda = request.form['ronda'].strip()

        # Calcular puntos automáticamente
        puntos_base = niveles.get(nivel, 0)
        multiplicador = mult_puntos.get(ronda, 0)
        puntos_calculados = puntos_base * multiplicador / 2

        # Actualizar historial
        jugador['historial'][index] = {
            'torneo': torneo,
            'fecha': fecha,
            'nivel': nivel,
            'pareja': pareja,
            'ronda': ronda,
            'puntos': puntos_calculados
        }

        # Recalcular puntos totales del jugador
        jugador['puntos'] = sum(item['puntos'] for item in jugador['historial'])

        guardar_jugadores_en_json()
        actualizar_ranking_json(jugadores)
        return redirect(url_for('historial', nombre=nombre))

    item = jugador['historial'][index]
    return render_template('editar_historial.html', jugador=jugador, item=item, index=index)

@app.route('/borrar_historial_item/<nombre>/<int:index>', methods=['GET'])
def borrar_historial_item(nombre, index):
    jugador = next((j for j in jugadores if j['nombre'] == nombre), None)

    if jugador and index < len(jugador.get('historial', [])):
        jugador['historial'].pop(index)
        jugador['puntos'] = sum(item['puntos'] for item in jugador['historial'])

        guardar_jugadores_en_json()
        actualizar_ranking_json(jugadores)

    return redirect(url_for('historial', nombre=nombre))

@app.route('/torneos')
def listar_torneos():
    try:
        with open('resultados.json', 'r') as f:
            resultados = json.load(f)
    except FileNotFoundError:
        resultados = []

    # Extraer torneos únicos por nombre + fecha + categoría
    torneos_unicos = []
    vistos = set()
    for r in resultados:
        clave = (r['torneo'], r['fecha'], r.get('categoria_torneo', 'SIN CATEGORIA'))
        if clave not in vistos:
            torneos_unicos.append({
                'torneo': r['torneo'],
                'fecha': r['fecha'],
                'nivel': r['nivel'],
                'categoria_torneo': r.get('categoria_torneo', 'SIN CATEGORIA')
            })
            vistos.add(clave)

    return render_template('torneos.html', torneos=torneos_unicos)


@app.route('/torneo/<nombre>/<fecha>/<categoria>')
def ver_torneo(nombre, fecha, categoria):
    try:
        with open('resultados.json', 'r') as f:
            resultados = json.load(f)
    except FileNotFoundError:
        resultados = []

    participantes = [
        r for r in resultados
        if r['torneo'] == nombre and r['fecha'] == fecha and r.get('categoria_torneo') == categoria
    ]

    return render_template('ver_torneo.html', nombre=nombre, fecha=fecha, categoria=categoria, participantes=participantes)


@app.route('/borrar_torneo/<nombre>/<fecha>/<categoria>', methods=['GET'])
def borrar_torneo(nombre, fecha, categoria):
    global jugadores

    # 1. Eliminar del archivo de resultados
    try:
        with open('resultados.json', 'r') as f:
            resultados = json.load(f)
    except FileNotFoundError:
        resultados = []

    nuevos_resultados = [
        r for r in resultados
        if not (
            r['torneo'] == nombre and
            r['fecha'] == fecha and
            r.get('categoria_torneo', '').upper() == categoria.upper()
        )
    ]

    with open('resultados.json', 'w') as f:
        json.dump(nuevos_resultados, f, indent=4)

    # 2. Eliminar del historial de cada jugador
    for j in jugadores:
        original = len(j.get('historial', []))
        j['historial'] = [
            h for h in j.get('historial', [])
            if not (
                h['torneo'] == nombre and
                h['fecha'] == fecha and
                h.get('categoria_torneo', '').upper() == categoria.upper()
            )
        ]
        if len(j['historial']) < original:
            j['puntos'] = sum(h['puntos'] for h in j['historial'])

    guardar_jugadores_en_json()
    actualizar_ranking_json(jugadores)

    return redirect(url_for('listar_torneos'))

@app.route('/agregar_jugadores', methods=['GET'])
def mostrar_formulario_jugadores():
    return render_template('agregar_jugadores.html')

@app.route('/agregar_jugadores', methods=['POST']) 
def agregar_jugadores():
    categoria = request.form['categoria'].strip()
    localidad = request.form['localidad'].strip()
    provincia = request.form['provincia'].strip()
    nombres_raw = request.form['nombres'].strip()

    # Separar por líneas, limpiar y pasar a mayúsculas
    nombres = [n.strip().upper() for n in nombres_raw.split('\n') if n.strip()]

    for nombre in nombres:
        # Evitar duplicados
        if any(j['nombre'] == nombre for j in jugadores):
            continue

        jugadores.append({
            'nombre': nombre,
            'categoria': categoria,
            'localidad': localidad,
            'provincia': provincia,
            'puntos': 0,
            'historial': []
        })

    guardar_jugadores_en_json()
    actualizar_ranking_json(jugadores)

    return redirect(url_for('index'))

@app.route('/corregir_nombre_torneo', methods=['POST'])
def corregir_nombre_torneo():
    nombre_actual = request.form['nombre_actual'].strip()
    nombre_nuevo = request.form['nombre_nuevo'].strip()

    # 1. Actualizar en resultados.json
    try:
        with open('resultados.json', 'r') as f:
            resultados = json.load(f)
    except FileNotFoundError:
        resultados = []

    for r in resultados:
        if r['torneo'] == nombre_actual:
            r['torneo'] = nombre_nuevo

    with open('resultados.json', 'w') as f:
        json.dump(resultados, f, indent=4)

    # 2. Actualizar en historial de jugadores
    for jugador in jugadores:
        for h in jugador.get('historial', []):
            if h['torneo'] == nombre_actual:
                h['torneo'] = nombre_nuevo

    guardar_jugadores_en_json()
    actualizar_ranking_json(jugadores)

    return f"Torneo '{nombre_actual}' fue corregido a '{nombre_nuevo}' exitosamente."

@app.route('/corregir_nombre_torneo_form', methods=['GET'])
def corregir_nombre_torneo_form():
    return render_template('corregir_torneo.html')

@app.route('/corregir_categoria_torneo', methods=['POST'])
def corregir_categoria_torneo():
    categoria_actual = request.form['categoria_actual'].strip()
    categoria_nueva = request.form['categoria_nueva'].strip()

    # 1. Corregir en resultados.json
    try:
        with open('resultados.json', 'r') as f:
            resultados = json.load(f)
    except FileNotFoundError:
        resultados = []

    for r in resultados:
        if r.get('categoria_torneo', '').upper() == categoria_actual.upper():
            r['categoria_torneo'] = categoria_nueva

    with open('resultados.json', 'w') as f:
        json.dump(resultados, f, indent=4)

    # 2. Corregir en historial de jugadores
    for jugador in jugadores:
        for h in jugador.get('historial', []):
            if h.get('categoria_torneo', '').upper() == categoria_actual.upper():
                h['categoria_torneo'] = categoria_nueva

    guardar_jugadores_en_json()
    actualizar_ranking_json(jugadores)

    return f"Categoría '{categoria_actual}' fue corregida a '{categoria_nueva}' exitosamente."

@app.route('/actualizar_jugadores_localidad_provincia')
def actualizar_jugadores_localidad_provincia():
    cambios = 0
    for jugador in jugadores:
        if 'localidad' not in jugador:
            jugador['localidad'] = 'Sin especificar'
            cambios += 1
        if 'provincia' not in jugador:
            jugador['provincia'] = 'Sin especificar'
            cambios += 1

    guardar_jugadores_en_json()
    return f"✅ Jugadores actualizados correctamente. Se realizaron {cambios} cambios."


@app.route('/grafico/<nombre>')
def grafico_jugador(nombre):
    jugador = next((j for j in jugadores if j['nombre'] == nombre), None)
    if not jugador:
        return "Jugador no encontrado", 404

    historial = sorted(jugador.get('historial', []), key=lambda x: x['fecha'])
    fechas = [h['fecha'] for h in historial]
    
    acumulado = []
    total = 0
    for h in historial:
        total += h['puntos']
        acumulado.append(total)

    return render_template('grafico_jugador.html',
                           nombre=nombre,
                           fechas=fechas,
                           puntos=acumulado)

@app.route('/criterios_rap')
def criterios_rap():
    return render_template('criterios_rap.html')

@app.route('/reglamento')
def reglamento():
    return render_template('reglamento.html')

if __name__ == '__main__':
    cargar_jugadores_desde_json()
    app.run(host='0.0.0.0', port=10000)

