from flask import Flask, render_template, request, redirect, url_for, session, flash
from collections import defaultdict
from datetime import datetime
import json
import os
import sqlite3


def get_db_connection():
    db_path = os.path.join(os.path.dirname(__file__), 'database.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn



def importar_historial_desde_json():
    if not os.path.exists('jugadores.json'):
        print("⚠️ Archivo jugadores.json no encontrado.")
        return

    with open('jugadores.json', 'r', encoding='utf-8') as f:
        datos_json = json.load(f)

    conn = get_db_connection()
    cursor = conn.cursor()

    actualizados = 0
    for jugador in datos_json:
        nombre = jugador.get("nombre", "").strip()
        historial = jugador.get("historial", [])

        if not nombre:
            continue

        historial_str = json.dumps(historial, ensure_ascii=False)

        cursor.execute("""
            UPDATE jugadores
            SET historial = ?
            WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(?))
        """, (historial_str, nombre))

        if cursor.rowcount > 0:
            actualizados += 1

    conn.commit()
    conn.close()
    print(f"✅ Historial importado en {actualizados} jugadores.")


def crear_tabla_jugadores():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jugadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            categoria TEXT,
            localidad TEXT,
            provincia TEXT,
            puntos INTEGER DEFAULT 0,
            historial TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("🛠️ Se creó o confirmó la tabla 'jugadores'")

def crear_tabla_resultados():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
      CREATE TABLE IF NOT EXISTS resultados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        torneo TEXT,
        fecha TEXT,
        nivel TEXT,
        categoria_torneo TEXT,
        jugador TEXT,
        pareja TEXT,
        ronda TEXT,
        puntos REAL,
        observacion TEXT
      )
    ''')
    conn.commit()
    conn.close()
    print("🛠️ Se creó o confirmó la tabla 'resultados'")


def asegurar_columnas_localidad_provincia():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE jugadores ADD COLUMN localidad TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        # ya existía
        pass
    try:
        cursor.execute("ALTER TABLE jugadores ADD COLUMN provincia TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        # ya existía
        pass
    conn.commit()
    conn.close()

def migrar_jugadores_json_a_sqlite():
    if not os.path.exists('jugadores.json'):
        print("⚠️ No se encontró jugadores.json. No se migró nada.")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM jugadores')
    if cursor.fetchone()[0] > 0:
        print("ℹ️ Jugadores ya cargados en la base. No se migró para evitar duplicados.")
        conn.close()
        return

    with open('jugadores.json', 'r', encoding='utf-8') as f:
        datos = json.load(f)

    for jugador in datos:
        cursor.execute('''
            INSERT INTO jugadores (nombre, categoria, localidad, provincia, puntos, historial)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            jugador.get('nombre'),
            jugador.get('categoria', ''),
            jugador.get('localidad', ''),
            jugador.get('provincia', ''),
            jugador.get('puntos', 0),
            json.dumps(jugador.get('historial', []), ensure_ascii=False)
        ))

    conn.commit()
    conn.close()
    print(f"✅ Se migraron {len(datos)} jugadores desde jugadores.json a SQLite.")




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

def calcular_ranking_temporada(jugadores_data=None, cantidad_maxima=10, ignorar_liga=False):
    """
    Calcula el ranking anual de los jugadores.
    - jugadores_data: lista opcional de dicts con keys "nombre","categoria","historial".
                      Si no se provee, se extrae de la BD.
    - cantidad_maxima: cuántos torneos mejores contar (por default 10).
    - ignorar_liga: si True, excluye los torneos de categoría "LIGA" al seleccionar los mejores.
    """
    # 1) Cargar lista de jugadores (ya filtrada o desde la BD)
    if jugadores_data is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT nombre, categoria, historial FROM jugadores")
        rows = cursor.fetchall()
        conn.close()

        jugadores = []
        for row in rows:
            historial = json.loads(row["historial"]) if row["historial"] else []
            jugadores.append({
                "nombre": row["nombre"],
                "categoria": row["categoria"],
                "historial": historial
            })
    else:
        jugadores = jugadores_data

    # 2) Calcular ranking para el año en curso
    ranking = []
    anio_actual = datetime.today().year

    for jugador in jugadores:
        historial = jugador.get("historial", [])

        # Filtrar solo torneos de este año
        anuales = [
            h for h in historial
            if datetime.strptime(h["fecha"], "%Y-%m-%d").year == anio_actual
        ]

        # Separar LIGA y no-LIGA
        torneos_no_liga = [h for h in anuales if h.get("categoria_torneo", "") != "LIGA"]
        torneos_para_top = torneos_no_liga if ignorar_liga else anuales

        # Tomar los mejores N torneos
        mejores = sorted(torneos_para_top, key=lambda x: x["puntos"], reverse=True)[:cantidad_maxima]
        total = sum(h["puntos"] for h in mejores)
        mejor_torneo = mejores[0]["puntos"] if mejores else 0

        # Puntos totales del año (incluyendo LIGA siempre)
        puntos_totales_anuales = sum(h["puntos"] for h in anuales)

        ranking.append({
            "nombre": jugador["nombre"],
            "categoria": jugador["categoria"],
            "puntos": total,
            "torneos_contados": len(mejores),
            "mejor_torneo": mejor_torneo,
            "puntos_totales_anuales": puntos_totales_anuales
        })

    # 3) Ordenar con criterios de desempate
    ranking_ordenado = sorted(
        ranking,
        key=lambda x: (
            -x["puntos"],
            -x["torneos_contados"],
            -x["mejor_torneo"],
            x["nombre"]
        )
    )

    return ranking_ordenado





@app.route('/')
def index():
    if not session.get('sigue_instagram'):
        return redirect(url_for('verificar_instagram'))

    # Filtros desde query string
    categoria_filtrada = request.args.get('categoria')
    provincia_filtrada = request.args.get('provincia')
    localidad_filtrada = request.args.get('localidad')
    nombre_filtrado   = request.args.get('nombre')

    # Conexión y consulta
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1) Traigo todos los jugadores para construir el ranking global
    todos_rows = cursor.execute(
        "SELECT nombre, categoria, provincia, localidad, historial, puntos FROM jugadores"
    ).fetchall()

    # 2) Traigo también solo los que necesito para poblar los selects y los filtros
    base_sql = """
        SELECT id, nombre, categoria, puntos, provincia, localidad, historial
        FROM jugadores WHERE 1=1
    """
    params = []
    if categoria_filtrada:
        base_sql += " AND categoria = ?"
        params.append(categoria_filtrada)
    if provincia_filtrada:
        base_sql += " AND LOWER(provincia) = ?"
        params.append(provincia_filtrada.lower())
    if localidad_filtrada:
        base_sql += " AND LOWER(localidad) = ?"
        params.append(localidad_filtrada.lower())

    jugadores_sql = cursor.execute(base_sql, params).fetchall()
    conn.close()

    # Helper: convertir fila a dict con historial parseado
    def procesar_fila(row):
        try:
            historial = json.loads(row["historial"]) if row["historial"] else []
        except json.JSONDecodeError:
            historial = []
        return {
            "nombre":    row["nombre"],
            "categoria": row["categoria"],
            "puntos":    float(row["puntos"]) if row["puntos"] is not None else 0.0,
            "provincia": row["provincia"] or "–",
            "localidad": row["localidad"] or "–",
            "historial": historial
        }

    todos_dict          = [procesar_fila(r) for r in todos_rows]
    jugadores_filtrados = [procesar_fila(r) for r in jugadores_sql]

    # 3) Construir ranking global con total anual y torneos contados
    anio_actual = datetime.today().year
    ranking = []
    for j in todos_dict:
        historiales_anio = [
            h for h in j["historial"]
            if datetime.strptime(h["fecha"], "%Y-%m-%d").year == anio_actual
        ]
        mejores = sorted(historiales_anio, key=lambda x: x["puntos"], reverse=True)[:6]
        total_anual      = sum(h["puntos"] for h in historiales_anio)
        torneos_contados = len(mejores)

        ranking.append({
            "nombre":           j["nombre"],
            "categoria":        j["categoria"],
            "puntos":           j["puntos"],
            "total_anual":      total_anual,
            "torneos_contados": torneos_contados,
            "provincia":        j["provincia"],
            "localidad":        j["localidad"],
            "posicion_real":    None
        })

    # 4) Ordenar por puntos y asignar posición_real
    ranking.sort(key=lambda x: x["puntos"], reverse=True)
    for idx, jugador in enumerate(ranking, start=1):
        jugador["posicion_real"] = idx

    # 5) Aplicar filtros sobre el ranking ya ordenado
    filtered = ranking
    if nombre_filtrado:
        nf = nombre_filtrado.strip().lower()
        filtered = [r for r in filtered if nf in r["nombre"].lower()]
    if categoria_filtrada:
        filtered = [r for r in filtered if r["categoria"] == categoria_filtrada]
    if provincia_filtrada:
        filtered = [r for r in filtered if r["provincia"].lower() == provincia_filtrada.lower()]
    if localidad_filtrada:
        filtered = [r for r in filtered if r["localidad"].lower() == localidad_filtrada.lower()]

    # 6) Preparar opciones de filtros (desde todos_dict)
    categorias_disponibles  = sorted({j["categoria"] for j in todos_dict if j["categoria"]})
    provincias_disponibles  = sorted({j["provincia"]  for j in todos_dict if j["provincia"]})
    localidades_disponibles = sorted({j["localidad"] for j in todos_dict if j["localidad"]})

    # 7) Logos de torneos
    ruta_logos = os.path.join('static','img','torneos')
    logos_torneos = []
    if os.path.exists(ruta_logos):
        logos_torneos = [f for f in os.listdir(ruta_logos)
                         if f.lower().endswith(('.png','.jpg','.jpeg','.webp'))]

    # 8) Torneos futuros
    try:
        with open('torneos_futuros.json','r',encoding='utf-8') as f:
            torneos_futuros = json.load(f)
    except FileNotFoundError:
        torneos_futuros = []

    hoy = datetime.today().date()
    torneos_futuros = [
        t for t in torneos_futuros
        if datetime.strptime(t["fecha"], "%Y-%m-%d").date() >= hoy
    ]

    return render_template(
        'index.html',
        year=datetime.today().year,
        jugadores=filtered,
        categorias=categorias_disponibles,
        provincias=provincias_disponibles,
        localidades=localidades_disponibles,
        categoria_actual=categoria_filtrada,
        provincia_actual=provincia_filtrada,
        localidad_actual=localidad_filtrada,
        nombre_actual=nombre_filtrado,
        logos_torneos=logos_torneos,
        torneos_futuros=torneos_futuros
    )








@app.route('/agregar_jugador', methods=['POST'])
def agregar_jugador():
    nombre = request.form['nombre'].strip().upper()
    categoria = request.form['categoria'].strip()
    localidad = request.form.get('localidad', '').strip()
    provincia = request.form.get('provincia', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO jugadores (nombre, categoria, localidad, provincia, puntos, historial)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (nombre, categoria, localidad, provincia, 0, json.dumps([])))
    conn.commit()
    conn.close()

    flash("Jugador agregado correctamente", "success")
    return redirect(url_for('index'))


@app.route('/editar_jugador/<nombre>', methods=['GET', 'POST'])
def editar_jugador(nombre):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    jugador = cursor.execute("SELECT * FROM jugadores WHERE LOWER(nombre) = ?", (nombre.lower(),)).fetchone()

    if not jugador:
        conn.close()
        flash("Jugador no encontrado", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        nuevo_nombre = request.form['nombre'].strip()
        nueva_categoria = request.form['categoria'].strip()
        nueva_localidad = request.form.get('localidad', '').strip()
        nueva_provincia = request.form.get('provincia', '').strip()

        cursor.execute("""
            UPDATE jugadores
            SET nombre = ?, categoria = ?, localidad = ?, provincia = ?
            WHERE LOWER(nombre) = ?
        """, (nuevo_nombre, nueva_categoria, nueva_localidad, nueva_provincia, nombre.lower()))
        conn.commit()
        conn.close()

        flash("Jugador actualizado correctamente", "success")
        return redirect(url_for('index'))

    jugador_dict = dict(jugador)
    conn.close()
    return render_template('editar_jugador.html', jugador=jugador_dict)




@app.route('/guardar_edicion_jugador', methods=['POST'])
def guardar_edicion_jugador():
    nombre_original = request.form['nombre_original'].strip()
    nuevo_nombre = request.form['nombre'].strip().upper()
    nueva_categoria = request.form['categoria'].strip()
    nueva_localidad = request.form.get('localidad', '').strip()
    nueva_provincia = request.form.get('provincia', '').strip()

    # Actualizar jugador en SQLite
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE jugadores
        SET nombre = ?, categoria = ?, localidad = ?, provincia = ?
        WHERE LOWER(nombre) = ?
    """, (nuevo_nombre, nueva_categoria, nueva_localidad, nueva_provincia, nombre_original.lower()))
    conn.commit()
    conn.close()

    # 🔁 También actualizar el nombre en historial_torneos.json
    try:
        with open('historial_torneos.json', 'r', encoding='utf-8') as f:
            historial_torneos = json.load(f)
    except FileNotFoundError:
        historial_torneos = []

    for torneo in historial_torneos:
        for resultado in torneo.get('resultados', []):
            if resultado.get('nombre') == nombre_original:
                resultado['nombre'] = nuevo_nombre

    with open('historial_torneos.json', 'w', encoding='utf-8') as f:
        json.dump(historial_torneos, f, indent=2, ensure_ascii=False)

    flash("Jugador actualizado correctamente", "success")
    return redirect(url_for('index'))

@app.route('/importar_resultados_externos', methods=['GET'])
def mostrar_formulario_importar():
    conn = get_db_connection()
    cursor = conn.cursor()
    jugadores = cursor.execute("SELECT nombre FROM jugadores").fetchall()
    conn.close()
    return render_template('importar_resultados_externos.html', jugadores=jugadores)


@app.route('/importar_resultado_externo_mejorado', methods=['POST'])
def importar_resultado_externo_mejorado():
    torneo = request.form['torneo'].strip()
    fecha = request.form['fecha'].strip()
    nivel = request.form['nivel'].strip().upper()
    categoria_torneo = request.form['categoria_torneo'].strip().upper()

    tipo_suma = "SUMA" in categoria_torneo
    limite_suma = None
    if tipo_suma:
        try:
            limite_suma = int(categoria_torneo.replace("SUMA", "").strip())
            print(f"✅ Torneo compensado detectado: SUMA {limite_suma}")
        except ValueError:
            tipo_suma = False
            print("⚠️ No se pudo interpretar el número en la categoría SUMA")

    instancias_form = request.form.getlist('instancia[]')
    jugadores_form = request.form.getlist('jugadores[]')
    coincidencias = []

    conn = get_db_connection()
    cursor = conn.cursor()

    for i in range(0, len(jugadores_form), 2):
        jugador1 = jugadores_form[i].strip().upper()
        jugador2 = jugadores_form[i + 1].strip().upper()
        instancia = instancias_form[i // 2].strip()
        if not jugador1 or not jugador2:
            continue

        # --- Calcular puntos ---
        puntos_base = niveles.get(nivel, 0) * (0.75 if tipo_suma else 1)
        multiplicador = mult_puntos.get(instancia, 0)
        puntos_totales = puntos_base * multiplicador
        puntos_por_jugador = puntos_totales / 2

        # --- Consultar dos filas ---
        j1 = cursor.execute("SELECT * FROM jugadores WHERE UPPER(nombre)=?", (jugador1,)).fetchone()
        j2 = cursor.execute("SELECT * FROM jugadores WHERE UPPER(nombre)=?", (jugador2,)).fetchone()
        jugador1_cat = j1["categoria"].upper() if j1 and j1["categoria"] else "SIN CATEGORIA"
        jugador2_cat = j2["categoria"].upper() if j2 and j2["categoria"] else "SIN CATEGORIA"

        # --- Validar torneo SUMA ---
        if tipo_suma and jugador1_cat != "SIN CATEGORIA" and jugador2_cat != "SIN CATEGORIA":
            try:
                num1 = int(''.join(filter(str.isdigit, jugador1_cat)))
                num2 = int(''.join(filter(str.isdigit, jugador2_cat)))
                suma_categorias = num1 + num2
                if suma_categorias < limite_suma:
                    for nombre in (jugador1, jugador2):
                        fila = cursor.execute("SELECT * FROM jugadores WHERE UPPER(nombre)=?", (nombre,)).fetchone()
                        if not fila:
                            continue
                        pareja = jugador2 if nombre == jugador1 else jugador1
                        historial = json.loads(fila['historial']) if fila['historial'] else []
                        historial.append({
                            'torneo': torneo,
                            'fecha': fecha,
                            'nivel': nivel,
                            'categoria_torneo': categoria_torneo,
                            'pareja': pareja,
                            'ronda': instancia,
                            'puntos': 0,
                            'observacion': f'No válido: suma de categorías ({num1}+{num2}={suma_categorias}) excede el límite ({limite_suma})'
                        })
                        cursor.execute(
                            "UPDATE jugadores SET historial=? WHERE id=?",
                            (json.dumps(historial, ensure_ascii=False), fila['id'])
                        )
                    conn.commit()
                    continue
            except ValueError:
                pass

        # --- Penalización tradicional ---
        if not tipo_suma:
            invalidos = []
            if jugador1_cat != "SIN CATEGORIA" and jugador1_cat < categoria_torneo:
                invalidos.append(jugador1)
            if jugador2_cat != "SIN CATEGORIA" and jugador2_cat < categoria_torneo:
                invalidos.append(jugador2)
            if invalidos:
                for nombre in (jugador1, jugador2):
                    fila = cursor.execute("SELECT * FROM jugadores WHERE UPPER(nombre)=?", (nombre,)).fetchone()
                    if not fila:
                        continue
                    pareja = jugador2 if nombre == jugador1 else jugador1
                    historial = json.loads(fila['historial']) if fila['historial'] else []
                    historial.append({
                        'torneo': torneo,
                        'fecha': fecha,
                        'nivel': nivel,
                        'categoria_torneo': categoria_torneo,
                        'pareja': pareja,
                        'ronda': instancia,
                        'puntos': 0,
                        'observacion': 'No válido: un jugador estaba en categoría inferior'
                    })
                    cursor.execute(
                        "UPDATE jugadores SET historial=? WHERE id=?",
                        (json.dumps(historial, ensure_ascii=False), fila['id'])
                    )
                conn.commit()
                continue

        # --- Coincidencias por apellido ---
        for nombre in (jugador1, jugador2):
            apellido = nombre.split()[-1]
            similares = cursor.execute(
                "SELECT nombre FROM jugadores WHERE nombre LIKE ? AND UPPER(nombre)!=?",
                (f"%{apellido}%", nombre)
            ).fetchall()
            if similares:
                coincidencias.append({
                    "nombre_ingresado": nombre,
                    "coincidencias": [s['nombre'] for s in similares]
                })

        # --- Guardar en historial y actualizar puntos ---
        for nombre in (jugador1, jugador2):
            pareja = jugador2 if nombre == jugador1 else jugador1
            fila = cursor.execute("SELECT * FROM jugadores WHERE UPPER(nombre)=?", (nombre,)).fetchone()

            # Si no existe, lo creamos antes de actualizar
            if not fila:
                cursor.execute("""
                    INSERT INTO jugadores (nombre, categoria, localidad, provincia, puntos, historial)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (nombre, 'Sin categoría', '', '', 0.0, json.dumps([])))
                conn.commit()
                fila = cursor.execute("SELECT * FROM jugadores WHERE UPPER(nombre)=?", (nombre,)).fetchone()

            historial = json.loads(fila['historial']) if fila['historial'] else []
            historial.append({
                'torneo': torneo,
                'fecha': fecha,
                'nivel': nivel,
                'categoria_torneo': categoria_torneo,
                'pareja': pareja,
                'ronda': instancia,
                'puntos': puntos_por_jugador
            })

            existentes = 0.0
            try:
                existentes = float(fila['puntos'])
            except (TypeError, ValueError):
                pass

            nuevo_total = existentes + puntos_por_jugador
            cursor.execute("""
                UPDATE jugadores SET puntos=?, historial=? WHERE id=?
            """, (nuevo_total, json.dumps(historial, ensure_ascii=False), fila['id']))
            conn.commit()

        # --- También guardamos en la tabla resultados ---
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

    conn.close()
    if coincidencias:
        session['coincidencias_apellido'] = coincidencias
    else:
        session.pop('coincidencias_apellido', None)

    return redirect(url_for('index'))




@app.route('/importar_resultado_externo')
def redireccion_legacy():
    return redirect(url_for('mostrar_formulario_importar'))




@app.route('/eliminar_jugador/<nombre>')
def eliminar_jugador(nombre):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Buscar por nombre exacto sin importar mayúsculas/minúsculas
    cursor.execute("DELETE FROM jugadores WHERE LOWER(nombre) = ?", (nombre.lower(),))
    conn.commit()
    conn.close()

    flash("Jugador eliminado correctamente", "success")
    return redirect(url_for('index'))


def guardar_resultado_en_historial(resultado):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Espera que resultado tenga estas claves:
    # 'torneo', 'fecha', 'nivel', 'categoria_torneo', 'instancia', 'jugadores', 'puntos_totales', 'puntos_por_jugador'
    torneo = resultado.get('torneo')
    fecha = resultado.get('fecha')
    nivel = resultado.get('nivel')
    categoria_torneo = resultado.get('categoria_torneo')
    instancia = resultado.get('instancia')
    jugadores = resultado.get('jugadores', [])
    puntos_por_jugador = resultado.get('puntos_por_jugador', 0)
    observacion = resultado.get('observacion', None)

    for jugador in jugadores:
        pareja = jugadores[1] if jugador == jugadores[0] else jugadores[0]
        cursor.execute('''
            INSERT INTO resultados (
                torneo, fecha, nivel, categoria_torneo,
                jugador, pareja, ronda, puntos, observacion
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            torneo, fecha, nivel, categoria_torneo,
            jugador, pareja, instancia, puntos_por_jugador, observacion
        ))

    conn.commit()
    conn.close()


def actualizar_ranking_sqlite(archivo='ranking.json'):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT nombre, puntos FROM jugadores ORDER BY puntos DESC")
    rows = cursor.fetchall()

    ranking = {row['nombre']: row['puntos'] for row in rows}

    with open(archivo, 'w') as f:
        json.dump(ranking, f, indent=4)

    conn.close()


def guardar_jugadores_en_json(archivo='jugadores.json'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jugadores")
    rows = cursor.fetchall()
    
    jugadores_export = []
    for row in rows:
        jugadores_export.append({
            'nombre': row['nombre'],
            'categoria': row['categoria'],
            'localidad': row['localidad'],
            'provincia': row['provincia'],
            'puntos': row['puntos'],
            'historial': json.loads(row['historial']) if row['historial'] else []
        })

    with open(archivo, 'w') as f:
        json.dump(jugadores_export, f, indent=4)

    conn.close()


def cargar_jugadores_desde_json(archivo='jugadores.json'):
    try:
        with open(archivo, 'r') as f:
            jugadores = json.load(f)
    except FileNotFoundError:
        print("Archivo jugadores.json no encontrado")
        return

    # Limpiar tabla
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jugadores")

    for j in jugadores:
        cursor.execute("""
            INSERT INTO jugadores (nombre, categoria, localidad, provincia, puntos, historial)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            j.get('nombre', ''),
            j.get('categoria', 'Sin categoría'),
            j.get('localidad', ''),
            j.get('provincia', ''),
            j.get('puntos', 0),
            json.dumps(j.get('historial', []))
        ))

    conn.commit()
    conn.close()
    print("Jugadores importados desde JSON a la base de datos")


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
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Traer jugadores de esa categoría
    cursor.execute("SELECT * FROM jugadores WHERE categoria = ?", (categoria,))
    rows = cursor.fetchall()
    conn.close()

    jugadores_categoria = []
    for row in rows:
        historial = json.loads(row['historial']) if row['historial'] else []
        jugadores_categoria.append({
            'nombre': row['nombre'],
            'categoria': row['categoria'],
            'localidad': row['localidad'],
            'provincia': row['provincia'],
            'puntos': row['puntos'],
            'historial': historial
        })

    # Calculamos el ranking temporal ignorando torneos tipo liga
    ranking_base = calcular_ranking_temporada(jugadores_categoria, cantidad_maxima=6, ignorar_liga=True)

    # Ya viene todo (nombre, puntos, localidad, provincia) en el mismo dict
    return render_template('ranking_categoria.html', jugadores=ranking_base, categoria_actual=categoria)



@app.route('/editar_historial/<nombre>/<int:index>', methods=['GET', 'POST'])
def editar_historial(nombre, index):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    row = cursor.execute("SELECT * FROM jugadores WHERE nombre = ?", (nombre,)).fetchone()

    if not row:
        conn.close()
        flash("Jugador no encontrado", "danger")
        return redirect(url_for('index'))

    historial = json.loads(row['historial']) if row['historial'] else []

    if index >= len(historial):
        conn.close()
        flash("Índice fuera de rango en historial", "danger")
        return redirect(url_for('historial', nombre=nombre))

    if request.method == 'POST':
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
        historial[index] = {
            'torneo': torneo,
            'fecha': fecha,
            'nivel': nivel,
            'pareja': pareja,
            'ronda': ronda,
            'puntos': puntos_calculados
        }

        # Recalcular puntos totales
        nuevos_puntos = sum(item['puntos'] for item in historial)

        # Guardar en base
        cursor.execute("""
            UPDATE jugadores SET historial = ?, puntos = ? WHERE id = ?
        """, (json.dumps(historial), nuevos_puntos, row['id']))
        conn.commit()
        conn.close()

        flash("Historial actualizado correctamente", "success")
        return redirect(url_for('historial', nombre=nombre))

    item = historial[index]
    jugador_dict = dict(row)
    jugador_dict['historial'] = historial
    conn.close()
    return render_template('editar_historial.html', jugador=jugador_dict, item=item, index=index)


@app.route('/borrar_historial_item/<nombre>/<int:index>', methods=['GET'])
def borrar_historial_item(nombre, index):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    row = cursor.execute("SELECT * FROM jugadores WHERE nombre = ?", (nombre,)).fetchone()

    if row:
        historial = json.loads(row['historial']) if row['historial'] else []

        if index < len(historial):
            historial.pop(index)
            nuevos_puntos = sum(item['puntos'] for item in historial)

            cursor.execute("""
                UPDATE jugadores
                SET historial = ?, puntos = ?
                WHERE id = ?
            """, (json.dumps(historial), nuevos_puntos, row['id']))
            conn.commit()

    conn.close()
    return redirect(url_for('historial', nombre=nombre))


@app.route('/torneos')
def listar_torneos():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT torneo, fecha, categoria_torneo, nivel, COUNT(*) as parejas
        FROM resultados
        GROUP BY torneo, fecha, categoria_torneo, nivel
        ORDER BY fecha DESC
    """)
    
    torneos = [
        {
            'torneo': row[0],
            'fecha': row[1],
            'categoria_torneo': row[2] if row[2] else 'SIN CATEGORIA',
            'nivel': row[3],
            'parejas': row[4]
        }
        for row in cursor.fetchall()
    ]

    conn.close()
    return render_template('torneos.html', torneos=torneos)



@app.route('/torneo/<nombre>/<fecha>/<categoria>')
def ver_torneo(nombre, fecha, categoria):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT jugador, pareja, ronda, puntos, nivel
        FROM resultados
        WHERE torneo = ? AND fecha = ? AND categoria_torneo = ?
    """, (nombre, fecha, categoria))

    participantes = [
        {
            'jugador': row['jugador'],
            'pareja': row['pareja'],
            'ronda': row['ronda'],
            'puntos': row['puntos'],
            'nivel': row['nivel']
        }
        for row in cursor.fetchall()
    ]

    conn.close()
    return render_template(
        'ver_torneo.html',
        nombre=nombre,
        fecha=fecha,
        categoria=categoria,
        participantes=participantes
    )


@app.route('/borrar_torneo/<nombre>/<fecha>/<categoria>', methods=['GET'])
def borrar_torneo(nombre, fecha, categoria):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Verificar si hay resultados que coincidan
    cursor.execute("""
        SELECT COUNT(*) FROM resultados
        WHERE torneo = ? AND fecha = ? AND UPPER(categoria_torneo) = ?
    """, (nombre, fecha, categoria.upper()))
    cantidad = cursor.fetchone()[0]

    if cantidad == 0:
        conn.close()
        flash("No se encontraron resultados para ese torneo.", "warning")
        return redirect(url_for('listar_torneos'))

    # 2. Borrar los resultados del torneo
    cursor.execute("""
        DELETE FROM resultados
        WHERE torneo = ? AND fecha = ? AND UPPER(categoria_torneo) = ?
    """, (nombre, fecha, categoria.upper()))
    conn.commit()

    # 3. Recalcular puntos e historial de todos los jugadores
    cursor.execute("SELECT * FROM jugadores")
    jugadores_rows = cursor.fetchall()

    for row in jugadores_rows:
        nombre_jugador = row['nombre']
        cursor.execute("""
            SELECT * FROM resultados
            WHERE jugador = ?
        """, (nombre_jugador,))
        historial = [dict(h) for h in cursor.fetchall()]  # Convertir a diccionarios

        historial_json = []
        total_puntos = 0

        for h in historial:
            historial_json.append({
                'torneo': h.get('torneo', ''),
                'fecha': h.get('fecha', ''),
                'nivel': h.get('nivel', ''),
                'categoria_torneo': h.get('categoria_torneo', 'SIN CATEGORIA'),
                'pareja': h.get('pareja', ''),
                'ronda': h.get('ronda', ''),
                'puntos': h.get('puntos', 0)
            })
            total_puntos += h.get('puntos', 0)

        cursor.execute("""
            UPDATE jugadores
            SET puntos = ?, historial = ?
            WHERE id = ?
        """, (total_puntos, json.dumps(historial_json, ensure_ascii=False), row['id']))

    conn.commit()
    conn.close()
    return redirect(url_for('listar_torneos'))


@app.route('/agregar_jugadores', methods=['GET', 'POST'])
def agregar_jugadores():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()

        categoria = request.form['categoria'].strip()
        localidad = request.form['localidad'].strip()
        provincia = request.form['provincia'].strip()
        nombres_raw = request.form.getlist('nombres[]')
        nombres = [n.strip().upper() for n in nombres_raw if n.strip()]

        nombres_existentes = []
        nombres_agregados = []
        posibles_coincidencias = {}

        for nombre in nombres:
            # Verificamos si ya existe
            cursor.execute("SELECT * FROM jugadores WHERE UPPER(nombre) = ?", (nombre,))
            existente = cursor.fetchone()

            if existente:
                nombres_existentes.append(nombre)
                continue

            # Insertamos nuevo jugador
            cursor.execute("""
                INSERT INTO jugadores (nombre, categoria, localidad, provincia, puntos, historial)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nombre, categoria, localidad, provincia, 0, json.dumps([])))
            nombres_agregados.append(nombre)

            # Buscar coincidencias por apellido
            if ' ' not in nombre:
                cursor.execute("SELECT nombre FROM jugadores WHERE nombre LIKE ? AND UPPER(nombre) != ?", (f"%{nombre}%", nombre))
                coincidencias = [row[0] for row in cursor.fetchall()]
                if coincidencias:
                    posibles_coincidencias[nombre] = coincidencias

        conn.commit()
        conn.close()

        session['nombres_existentes'] = nombres_existentes
        session['nombres_agregados'] = nombres_agregados
        session['coincidencias_apellido'] = posibles_coincidencias

        return redirect(url_for('index'))

    # GET → Mostrar formulario
    return render_template("agregar_jugadores.html")



@app.route('/corregir_nombre_torneo', methods=['POST'])
def corregir_nombre_torneo():
    nombre_actual = request.form['nombre_actual'].strip()
    nombre_nuevo = request.form['nombre_nuevo'].strip()

    # 1. Actualizar en resultados.json
    try:
        with open('resultados.json', 'r', encoding='utf-8') as f:
            resultados = json.load(f)
    except FileNotFoundError:
        resultados = []

    cambios_realizados = 0
    for r in resultados:
        if r.get('torneo') == nombre_actual:
            r['torneo'] = nombre_nuevo
            cambios_realizados += 1

    with open('resultados.json', 'w', encoding='utf-8') as f:
        json.dump(resultados, f, indent=4, ensure_ascii=False)

    # 2. Actualizar en historial de jugadores (lista global en memoria)
    cambios_historial = 0
    for jugador in jugadores:
        for h in jugador.get('historial', []):
            if h.get('torneo') == nombre_actual:
                h['torneo'] = nombre_nuevo
                cambios_historial += 1

    guardar_jugadores_en_json()
    actualizar_ranking_json(jugadores)

    mensaje = f"Torneo actualizado: '{nombre_actual}' → '{nombre_nuevo}'. Se actualizaron {cambios_realizados} resultados y {cambios_historial} items de historial."
    flash(mensaje, "success")
    return redirect(url_for('index'))

@app.route('/corregir_nombre_torneo_form', methods=['GET'])
def corregir_nombre_torneo_form():
    return render_template('corregir_torneo.html')

@app.route('/corregir_categoria_torneo', methods=['POST'])
def corregir_categoria_torneo():
    categoria_actual = request.form['categoria_actual'].strip()
    categoria_nueva = request.form['categoria_nueva'].strip()

    # 1. Corregir en resultados.json
    try:
        with open('resultados.json', 'r', encoding='utf-8') as f:
            resultados = json.load(f)
    except FileNotFoundError:
        resultados = []

    cambios_resultados = 0
    for r in resultados:
        if r.get('categoria_torneo', '').upper() == categoria_actual.upper():
            r['categoria_torneo'] = categoria_nueva
            cambios_resultados += 1

    with open('resultados.json', 'w', encoding='utf-8') as f:
        json.dump(resultados, f, indent=4, ensure_ascii=False)

    # 2. Corregir en historial de jugadores
    cambios_historial = 0
    for jugador in jugadores:
        for h in jugador.get('historial', []):
            if h.get('categoria_torneo', '').upper() == categoria_actual.upper():
                h['categoria_torneo'] = categoria_nueva
                cambios_historial += 1

    guardar_jugadores_en_json()
    actualizar_ranking_json(jugadores)

    mensaje = f"Categoría actualizada: '{categoria_actual}' → '{categoria_nueva}'. Se modificaron {cambios_resultados} resultados y {cambios_historial} en historial."
    flash(mensaje, "success")
    return redirect(url_for('index'))


@app.route('/unificar_jugadores', methods=['GET', 'POST'])
def unificar_jugadores():
    if request.method == 'POST':
        nombre_base = request.form['jugador_base'].strip().upper()
        nombre_duplicado = request.form['jugador_duplicado'].strip().upper()

        conn = get_db_connection()
        cursor = conn.cursor()

        # 1) Buscamos ambos jugadores en la base
        cursor.execute("SELECT * FROM jugadores WHERE UPPER(nombre) = ?", (nombre_base,))
        base = cursor.fetchone()
        cursor.execute("SELECT * FROM jugadores WHERE UPPER(nombre) = ?", (nombre_duplicado,))
        duplicado = cursor.fetchone()

        if not base or not duplicado:
            conn.close()
            flash("Uno de los jugadores no se encontró en la base.", "danger")
            return redirect(url_for('unificar_jugadores'))

        # 2) Cargamos históricos y puntos
        historial_base = json.loads(base['historial']) if base['historial'] else []
        historial_dup  = json.loads(duplicado['historial']) if duplicado['historial'] else []

        puntos_base = float(base['puntos'] or 0)
        puntos_dup  = float(duplicado['puntos'] or 0)

        # 3) Sumamos puntos
        nuevos_puntos = puntos_base + puntos_dup

        # 4) Unificamos historial sin duplicar torneos (mismo torneo+fecha)
        claves = {(h['torneo'], h['fecha']) for h in historial_base}
        añadidos = [h for h in historial_dup if (h['torneo'], h['fecha']) not in claves]
        nuevo_historial = historial_base + añadidos

        # 5) Actualizamos el registro base
        cursor.execute("""
            UPDATE jugadores
            SET puntos = ?, historial = ?
            WHERE id = ?
        """, (
            nuevos_puntos,
            json.dumps(nuevo_historial, ensure_ascii=False),
            base['id']
        ))

        # 6) Borramos el registro duplicado
        cursor.execute("DELETE FROM jugadores WHERE id = ?", (duplicado['id'],))

        conn.commit()
        conn.close()

        flash("Jugadores unificados con éxito.", "success")
        return redirect(url_for('unificar_jugadores'))

    # GET → mostramos el formulario con todos los jugadores
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nombre FROM jugadores ORDER BY nombre")
    opciones = [row['nombre'] for row in cursor.fetchall()]
    conn.close()

    return render_template('unificar_jugadores.html', jugadores=opciones)



@app.route('/actualizar_jugadores_localidad_provincia')
def actualizar_jugadores_localidad_provincia():
    cambios = 0
    for jugador in jugadores:
        if 'localidad' not in jugador or not jugador['localidad']:
            jugador['localidad'] = 'Sin especificar'
            cambios += 1
        if 'provincia' not in jugador or not jugador['provincia']:
            jugador['provincia'] = 'Sin especificar'
            cambios += 1

    guardar_jugadores_en_json()
    actualizar_ranking_json(jugadores)
    return f"✅ Jugadores actualizados correctamente. Se realizaron {cambios} cambios."



@app.route('/perfil/<nombre>')
def perfil_jugador(nombre):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Normalización para evitar errores con tildes, mayúsculas, etc.
    nombre_normalizado = nombre.strip().lower()

    jugadores = cursor.execute("SELECT * FROM jugadores").fetchall()
    jugador = next((j for j in jugadores if j['nombre'].strip().lower() == nombre_normalizado), None)

    if not jugador:
        conn.close()
        return "Jugador no encontrado", 404

    # Cargar historial desde la base (guardado como JSON string)
    historial_json = jugador["historial"]
    historial = json.loads(historial_json) if historial_json else []

    # Ordenar historial por fecha
    historial = sorted(historial, key=lambda x: x['fecha'])
    fechas = [h['fecha'] for h in historial]

    acumulado = []
    total = 0
    for h in historial:
        total += h['puntos']
        acumulado.append(total)

    puntos_totales = sum(h['puntos'] for h in historial)
    mejor_torneo = max((h['puntos'] for h in historial), default=0)
    torneos_jugados = len(historial)

    conn.close()

    return render_template('perfil_jugador.html',
                           jugador=jugador,
                           historial=historial,
                           fechas=fechas,
                           puntos=acumulado,
                           puntos_totales=puntos_totales,
                           mejor_torneo=mejor_torneo,
                           torneos_jugados=torneos_jugados)

@app.route('/criterios_rap')
def criterios_rap():
    return render_template('criterios_rap.html')

@app.route('/reglamento')
def reglamento():
    return render_template('reglamento.html')

@app.route('/calendario')
def calendario_torneos():
    try:
        with open('torneos_futuros.json', 'r') as f:
            torneos = json.load(f)
    except FileNotFoundError:
        torneos = []

    # Ordenar por fecha
    torneos = sorted(torneos, key=lambda x: x['fecha'])

    return render_template('calendario.html', torneos=torneos)


@app.route('/agregar_torneo_futuro', methods=['GET', 'POST'])
def agregar_torneo_futuro():
    if not session.get('es_admin'):
        return "Acceso denegado", 403

    if request.method == 'POST':
        nuevo_torneo = {
            'nombre': request.form['nombre'].strip(),
            'fecha': request.form['fecha'],
            'localidad': request.form['localidad'].strip(),
            'provincia': request.form['provincia'].strip(),
            'instagram': request.form.get('instagram', '').strip(),
            'nivel': request.form['nivel'].strip().upper()
        }

        try:
            with open('torneos_futuros.json', 'r') as f:
                torneos = json.load(f)
        except FileNotFoundError:
            torneos = []

        torneos.append(nuevo_torneo)

        with open('torneos_futuros.json', 'w') as f:
            json.dump(torneos, f, indent=4)

        return redirect(url_for('calendario_torneos'))

    return render_template('agregar_torneo_futuro.html')

@app.route('/verificar_instagram', methods=['GET', 'POST'])
def verificar_instagram():
    if request.method == 'POST':
        session['sigue_instagram'] = True  # guardamos que ya "sigue"
        return redirect(url_for('index'))  # lo mandamos al ranking
    return render_template('verificar_instagram.html')

@app.route('/revisar_jugadores', methods=['GET', 'POST'])
def revisar_jugadores():
    if not session.get('es_admin'):
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        nombre = request.form['nombre']
        nueva_categoria = request.form['categoria']
        cursor.execute("UPDATE jugadores SET categoria = ? WHERE nombre = ?", (nueva_categoria, nombre))
        conn.commit()

    # Capturar todas las variantes posibles de "sin categoría"
    cursor.execute("""
        SELECT nombre, categoria
        FROM jugadores
        WHERE categoria IS NULL
           OR TRIM(categoria) = ''
           OR LOWER(REPLACE(categoria, 'í', 'i')) = 'sin categoria'
    """)
    jugadores_sin_categoria = cursor.fetchall()
    conn.close()

    return render_template('revisar_jugadores.html', jugadores=jugadores_sin_categoria)





@app.route('/editar_jugadores')
def editar_jugadores():
    if not session.get('es_admin'):
        return redirect(url_for('index'))

    nombre = request.args.get('nombre', '').lower()
    categoria = request.args.get('categoria')
    provincia = request.args.get('provincia')
    localidad = request.args.get('localidad')

    filtrados = jugadores
    if nombre:
        filtrados = [j for j in filtrados if nombre in j['nombre'].lower()]
    if categoria:
        filtrados = [j for j in filtrados if j.get('categoria') == categoria]
    if provincia:
        filtrados = [j for j in filtrados if j.get('provincia', '').lower() == provincia.lower()]
    if localidad:
        filtrados = [j for j in filtrados if j.get('localidad', '').lower() == localidad.lower()]

    filtrados_ordenados = sorted(filtrados, key=lambda j: j['nombre'].lower())

    categorias = sorted(set(j['categoria'] for j in jugadores if j.get('categoria')))
    provincias = sorted(set(j['provincia'] for j in jugadores if j.get('provincia')))
    localidades = sorted(set(j['localidad'] for j in jugadores if j.get('localidad')))

    return render_template(
        'editar_jugadores.html',
        jugadores=filtrados_ordenados,
        categorias=categorias,
        provincias=provincias,
        localidades=localidades
    )


def asegurar_columna_historial():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE jugadores ADD COLUMN historial TEXT")
        conn.commit()
        print("✅ Se agregó la columna 'historial'")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ La columna 'historial' ya existe.")
        else:
            print("❌ Error al agregar la columna 'historial':", e)

    conn.close()



def migrar_puntos_desde_ranking():
    if not os.path.exists('ranking.json'):
        print("⚠️ No se encontró ranking.json. No se cargaron puntos.")
        return

    with open('ranking.json', 'r', encoding='utf-8') as f:
        ranking = json.load(f)

    conn = get_db_connection()
    cursor = conn.cursor()

    for jugador in ranking:
        nombre_normalizado = jugador.get('nombre', '').strip().upper()
        puntos = jugador.get('puntos', 0)
        cursor.execute("UPDATE jugadores SET puntos = ? WHERE UPPER(nombre) = ?", (puntos, nombre_normalizado))

    conn.commit()
    conn.close()
    print("✅ Puntos actualizados desde ranking.json")

@app.route('/historial/<nombre>')
def historial(nombre):
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Buscar jugador exacto
    cursor.execute("SELECT * FROM jugadores WHERE UPPER(nombre) = ?", (nombre.upper(),))
    jugador = cursor.fetchone()

    if not jugador:
        conn.close()
        return f"No se encontró al jugador: {nombre}", 404

    # Cargar historial desde campo JSON
    try:
        historial = json.loads(jugador['historial'])
    except json.JSONDecodeError:
        historial = []

    conn.close()

    return render_template("historial.html", jugador=jugador, historial=historial)

def migrar_historial_torneos_json():
    if not os.path.exists('historial_torneos.json'):
        print("⚠️ No se encontró historial_torneos.json. No se migró nada.")
        return

    with open('historial_torneos.json', 'r', encoding='utf-8') as f:
        torneos = json.load(f)

    conn = get_db_connection()
    cursor = conn.cursor()
    migrados = 0

    for t in torneos:
        torneo = t.get('torneo')
        fecha = t.get('fecha')
        for r in t.get('resultados', []):
            cursor.execute('''
                INSERT INTO resultados (
                    torneo, fecha, nivel, categoria_torneo,
                    jugador, pareja, ronda, puntos, observacion
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                torneo,
                fecha,
                r.get('nivel'),
                r.get('categoria_torneo', ''),
                r.get('nombre'),
                r.get('pareja'),
                r.get('ronda'),
                r.get('puntos', 0),
                r.get('observacion')
            ))
            migrados += 1

    conn.commit()
    conn.close()
    print(f"✅ Se migraron {migrados} resultados desde historial_torneos.json a SQLite.")



if __name__ == '__main__':
    crear_tabla_jugadores()                  # 🟢 Crea la tabla si no existe
    crear_tabla_resultados()
    asegurar_columnas_localidad_provincia()
    migrar_jugadores_json_a_sqlite()         # 🟢 Inserta jugadores si la tabla está vacía
    asegurar_columna_historial()             # 🟢 Agrega columna 'historial' si falta
    migrar_puntos_desde_ranking()            # 🟢 Carga los puntos desde ranking.json
    migrar_historial_torneos_json()

    app.run(debug=True, host='0.0.0.0', port=10000)






