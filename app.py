from flask import Flask, render_template, request, redirect, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import os

app = Flask(__name__)
app.secret_key = "aerolinea"


def conectar():
    return pymysql.connect(
        host=os.environ.get("MYSQLHOST"),
        user=os.environ.get("MYSQLUSER"),
        password=os.environ.get("MYSQLPASSWORD"),
        database=os.environ.get("MYSQLDATABASE"),
        port=int(os.environ.get("MYSQLPORT")),
        cursorclass=pymysql.cursors.DictCursor
    )


@app.route('/')
def inicio():
    return render_template('index.html')


@app.route('/vuelos')
def vuelos():
    origen = request.args.get('origen', '')
    destino = request.args.get('destino', '')
    fecha = request.args.get('fecha', '')

    conexion = conectar()
    cursor = conexion.cursor()

    consulta = "SELECT * FROM vuelos WHERE 1=1"
    valores = []

    if origen:
        consulta += " AND origen LIKE %s"
        valores.append(f"%{origen}%")

    if destino:
        consulta += " AND destino LIKE %s"
        valores.append(f"%{destino}%")

    if fecha:
        consulta += " AND fecha = %s"
        valores.append(fecha)

    cursor.execute(consulta, valores)
    datos = cursor.fetchall()
    conexion.close()

    return render_template('vuelos.html', vuelos=datos)


@app.route('/reservar', methods=['GET', 'POST'])
def reservar():
    conexion = conectar()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM vuelos")
    vuelos = cursor.fetchall()

    asientos = list(range(1, 31))

    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        correo = request.form['correo']
        telefono = request.form['telefono']
        vuelo_id = request.form['vuelo_id']
        asiento = request.form['asiento']

        cursor.execute("SELECT asientos FROM vuelos WHERE id = %s", (vuelo_id,))
        vuelo = cursor.fetchone()

        if not vuelo:
            flash("El vuelo no existe")
            conexion.close()
            return redirect('/reservar')

        if vuelo['asientos'] <= 0:
            flash("No hay asientos disponibles")
            conexion.close()
            return redirect('/reservar')

        cursor.execute("""
            SELECT * FROM reservas
            WHERE vuelo_id = %s AND asiento = %s
        """, (vuelo_id, asiento))

        ocupado = cursor.fetchone()

        if ocupado:
            flash("Ese asiento ya está ocupado")
            conexion.close()
            return redirect('/reservar')

        cursor.execute("SELECT COUNT(*) AS total FROM reservas")
        total = cursor.fetchone()['total'] + 1

        codigo_reserva = f"RES-{total:04d}"

        cursor.execute("""
            INSERT INTO reservas
            (codigo_reserva, nombre, apellido, correo, telefono, vuelo_id, asiento)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (codigo_reserva, nombre, apellido, correo, telefono, vuelo_id, asiento))

        cursor.execute("""
            UPDATE vuelos
            SET asientos = asientos - 1
            WHERE id = %s
        """, (vuelo_id,))

        conexion.commit()
        conexion.close()

        flash(f"Reserva realizada correctamente. Código: {codigo_reserva}. Asiento: {asiento}")
        return redirect('/reservas')

    conexion.close()
    return render_template('reservar.html', vuelos=vuelos, asientos=asientos)


@app.route('/reservas')
def reservas():
    conexion = conectar()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT reservas.id,
               reservas.codigo_reserva,
               reservas.nombre,
               reservas.apellido,
               reservas.correo,
               reservas.telefono,
               reservas.asiento,
               vuelos.codigo_vuelo,
               vuelos.origen,
               vuelos.destino,
               vuelos.fecha,
               vuelos.hora
        FROM reservas
        INNER JOIN vuelos
        ON reservas.vuelo_id = vuelos.id
        ORDER BY reservas.id DESC
    """)

    datos = cursor.fetchall()
    conexion.close()

    return render_template('reservas.html', reservas=datos)


@app.route('/cancelar/<int:id>')
def cancelar(id):
    conexion = conectar()
    cursor = conexion.cursor()

    cursor.execute("SELECT vuelo_id FROM reservas WHERE id = %s", (id,))
    reserva = cursor.fetchone()

    if reserva:
        vuelo_id = reserva['vuelo_id']

        cursor.execute("""
            UPDATE vuelos
            SET asientos = asientos + 1
            WHERE id = %s
        """, (vuelo_id,))

        cursor.execute("DELETE FROM reservas WHERE id = %s", (id,))
        conexion.commit()

    conexion.close()

    flash("Reserva cancelada correctamente")
    return redirect('/reservas')


@app.route('/registro', methods=['GET', 'POST'])
def registro():

    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        correo = request.form['correo']
        telefono = request.form['telefono']
        password = request.form['password']

        password_segura = generate_password_hash(password)

        conexion = conectar()
        cursor = conexion.cursor()

        cursor.execute("SELECT * FROM usuarios WHERE correo = %s", (correo,))
        existe = cursor.fetchone()

        if existe:
            conexion.close()
            flash("Ese correo ya está registrado")
            return redirect('/registro')

        cursor.execute("""
            INSERT INTO usuarios(nombre, apellido, correo, telefono, password)
            VALUES (%s, %s, %s, %s, %s)
        """, (nombre, apellido, correo, telefono, password_segura))

        conexion.commit()
        conexion.close()

        flash("Te registraste con éxito. Ya puedes iniciar sesión.")
        return redirect('/login')

    return render_template('registro.html')


@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        correo = request.form['correo']
        password = request.form['password']

        conexion = conectar()
        cursor = conexion.cursor()

        cursor.execute("SELECT * FROM usuarios WHERE correo = %s", (correo,))
        usuario = cursor.fetchone()

        conexion.close()

        if usuario and check_password_hash(usuario['password'], password):
            session['usuario_id'] = usuario['id']
            session['usuario_nombre'] = usuario['nombre']
            session['usuario_rol'] = usuario['rol']

            flash("Inicio de sesión correcto")
            return redirect('/')

        flash("Correo o contraseña incorrectos")
        return redirect('/login')

    return render_template('login.html')

@app.route('/buscar_reserva', methods=['GET', 'POST'])
def buscar_reserva():

    reserva = None

    if request.method == 'POST':
        codigo = request.form['codigo_reserva']

        conexion = conectar()
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT reservas.codigo_reserva,
                   reservas.nombre,
                   reservas.apellido,
                   reservas.correo,
                   reservas.telefono,
                   reservas.asiento,
                   vuelos.codigo_vuelo,
                   vuelos.origen,
                   vuelos.destino,
                   vuelos.fecha,
                   vuelos.hora,
                   vuelos.estado
            FROM reservas
            INNER JOIN vuelos
            ON reservas.vuelo_id = vuelos.id
            WHERE reservas.codigo_reserva = %s
        """, (codigo,))

        reserva = cursor.fetchone()

        conexion.close()

        if not reserva:
            flash("No se encontró ninguna reserva con ese código")

    return render_template('buscar_reserva.html', reserva=reserva)


@app.route('/logout')
def logout():
    session.clear()
    flash("Sesión cerrada correctamente")
    return redirect('/')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)