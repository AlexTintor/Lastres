import os
import threading
import time
from flask import Flask, after_this_request, request, jsonify, send_file, send_from_directory
import smtplib, random
from email.message import EmailMessage
from flask_cors import CORS
import json
import pyodbc

# Importaciones locales
from bdEDDO import validarLogin, traerExpediente, traerReclamos, cambiarContra, cambiarContraActual, guardarMensaje, traerMsjs, registrarDoc, todosDocumentos, llenadoDoc
from bdTec import traerEmpleados, traerPlaza, validarDocenteTEC, traerDocumentosTEC
from bdEDD import validarRequisito # type: ignore
from convertirPdf import generar_constancia

app = Flask(__name__)
CORS(app)

# --- 1. CONFIGURACIÓN DE RUTAS DINÁMICAS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))      # .../Backend/back
RAIZ_PROYECTO = os.path.dirname(os.path.dirname(BASE_DIR)) # .../EDDO-main (Raíz)
CARPETA_DOCUMENTOS = os.path.join(RAIZ_PROYECTO, "Docs")
CARPETA_FIRMAS = os.path.join(RAIZ_PROYECTO, "Firmas") # Asegúrate que tu carpeta se llame "Firmas" o "firmas" (revisa mayúsculas)

# Crear carpeta de firmas si no existe
if not os.path.exists(CARPETA_FIRMAS):
    try:
        os.makedirs(CARPETA_FIRMAS)
    except:
        pass

print(f"📂 Docs configurado en: {CARPETA_DOCUMENTOS}")
print(f"📂 Firmas configurado en: {CARPETA_FIRMAS}")

def conectar_bd(bd):
    try:
        conexion = pyodbc.connect(
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER=localhost;'
            f'DATABASE={bd};'
            f'UID=irvin;'
            f'PWD=123;'
        )
        return conexion
    except Exception as e:
        print(f"❌ Error al conectar a la base de datos {bd}:", e)
        return None

# --- 2. RUTAS DE FIRMA DIGITAL ---

@app.route("/obtener-firma", methods=["POST"])
def obtener_firma():
    data = request.get_json()
    idUsuario = data.get("idUsuario")
    if not idUsuario: return jsonify({"estatus": False}), 400

    nombre = f"firma_{idUsuario}.png"
    ruta = os.path.join(CARPETA_FIRMAS, nombre)
    
    if os.path.exists(ruta):
        return jsonify({"estatus": True, "tieneFirma": True, "url": f"/firmas/{nombre}"})
    return jsonify({"estatus": True, "tieneFirma": False})

@app.route("/subir-firma", methods=["POST"])
def subir_firma():
    try:
        idUsuario = request.form.get("idUsuario")
        archivo = request.files.get("imagenFirma")
        if not idUsuario or not archivo: return jsonify({"estatus": False}), 400

        nombre = f"firma_{idUsuario}.png"
        ruta_guardado = os.path.join(CARPETA_FIRMAS, nombre)
        archivo.save(ruta_guardado)

        return jsonify({"estatus": True, "url": f"/firmas/{nombre}"})
    except Exception as e:
        return jsonify({"estatus": False, "error": str(e)}), 500

@app.route('/firmas/<path:filename>')
def serve_firmas(filename):
    return send_from_directory(CARPETA_FIRMAS, filename)

# --- 3. LOGIN CON VALIDACIÓN DE REQUISITOS (TIEMPO COMPLETO) ---

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    correo = data.get("correo")
    contra = data.get("contra")
    
    if not correo or not contra:
        return jsonify({"estatus": False, "error": "Faltan datos"}), 400

    print(f"🔑 Intentando login para: {correo}")

    # A. Validar Credenciales en EDDO
    conexion = conectar_bd("EDDO")
    if not conexion:
        return jsonify({"estatus": False, "error": "Error conexión EDDO"}), 500

    docente_id = validarLogin(conexion, correo, contra)
    conexion.close()

    if not docente_id:
        return jsonify({"estatus": False, "error": "Credenciales inválidas"}), 401

    # B. BLOQUEO DE SEGURIDAD: Validar perfil en BDTEC
    print(f"🔍 Verificando requisitos en BDTEC para {correo}...")
    conexion_tec = conectar_bd("BDTEC")
    
    if conexion_tec:
        try:
            cursor = conexion_tec.cursor()
            query = """
                SELECT P.HORARIO, E.VIGENCIA
                FROM EMPLEADO E
                INNER JOIN PLAZA P ON E.ID_PLAZA = P.ID_PLAZA
                WHERE E.CORREO = ?
            """
            cursor.execute(query, (correo,))
            row = cursor.fetchone()
            conexion_tec.close()

            if not row:
                return jsonify({"estatus": False, "error": "No tienes registro activo en el TEC"}), 403

            horario, vigencia = row
            
            # REGLA 1: Validar Tiempo Completo
            if "Tiempo Completo" not in str(horario):
                print(f"⛔ BLOQUEADO: Plaza '{horario}' no permitida.")
                return jsonify({
                    "estatus": False, 
                    "error": f"Tu plaza es '{horario}'. El sistema requiere 'Tiempo Completo'."
                }), 403

            # REGLA 2: Validar Vigencia
            es_vigente = False
            if str(vigencia) == "1" or str(vigencia).lower() in ["vigente", "true", "si"]:
                es_vigente = True
                
            if not es_vigente:
                print("⛔ BLOQUEADO: No está vigente.")
                return jsonify({"estatus": False, "error": "Tu estatus actual no es VIGENTE."}), 403

        except Exception as e:
            print(f"❌ Error validando requisitos: {e}")
            return jsonify({"estatus": False, "error": "Error interno validando requisitos"}), 500
    else:
        return jsonify({"estatus": False, "error": "No se pudo conectar a BDTEC para validar"}), 500

    print("✅ Login Exitoso: Cumple requisitos.")
    return jsonify({"estatus": True, "id_docente": docente_id})

# --- 4. RUTAS RESTANTES DEL SISTEMA ---

@app.route("/enviar-codigo", methods=["POST"])
def enviar_codigo():
    data = request.get_json()
    correo_destino = data.get("correo")
    if not correo_destino: return jsonify({"ok": False, "error": "No correo"}), 400

    codigo = random.randint(100000, 999999)
    # AJUSTA TUS CREDENCIALES SI CAMBIAN
    remitente = "vevovevo963@gmail.com"
    contraseña = "rryeyeztaugrbppy"

    msg = EmailMessage()
    msg["Subject"] = "Código de verificación"
    msg["From"] = remitente
    msg["To"] = correo_destino
    msg.set_content(f"Tu código de verificación es: {codigo}")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(remitente, contraseña)
            smtp.send_message(msg)
        return jsonify({"estatus": True, "codigo": codigo})
    except Exception as e:
        return jsonify({"estatus": False, "error": str(e)}), 500

@app.route("/expedient", methods=["POST"])
def expediente():
    data = request.get_json()
    idUsuario = data.get("idUsuario")
    conexion = conectar_bd("EDDO")
    if not conexion: return jsonify({"estatus": False}), 500
    expediente = traerExpediente(conexion, idUsuario)
    conexion.close()
    if expediente: return jsonify({"estatus": True, "expediente": expediente})
    return jsonify({"estatus": False, "error": "No encontrado"}), 404
    
@app.route("/todosDocumentos", methods=["POST"])
def todosDocu():
    conexion = conectar_bd("EDDO")
    if not conexion: return jsonify({"estatus": False}), 500
    documentos = todosDocumentos(conexion)
    conexion.close()
    if documentos: return jsonify({"estatus": True, "Documentos": documentos})
    return jsonify({"estatus": False}), 404

@app.route("/reclamos", methods=["POST"])
def reclamos():
    data = request.get_json()
    idUsuario = data.get("idUsuario")
    conexion = conectar_bd("EDDO")
    if not conexion: return jsonify({"estatus": False}), 500
    reclamos = traerReclamos(conexion, idUsuario)
    conexion.close()
    if reclamos: return jsonify({"estatus": True, "reclamos": reclamos})
    return jsonify({"estatus": False}), 404
    
@app.route("/registrarDocente", methods =["POST"])
def registrarDocente():
    data = request.get_json()
    correo = data.get("CORREO")
    contra = data.get("CONTRA")

    conexion2 = conectar_bd("BDTEC")
    if not conexion2: return jsonify({"estatus": False, "error": "Sin conexión TEC"}), 500
    
    if not validarDocenteTEC(conexion2, correo):
        return jsonify({"estatus": False, "error": "Correo no pertenece a docente TEC"}), 400
    
    datos = traerEmpleados(conexion2, correo, idDocente = 0)
    if not datos: return jsonify({"estatus": False, "error": "No datos TEC"}), 404
    
    if isinstance(datos, list) and len(datos) > 0: datos = datos[0]
    
    conexion2.close()
    
    conexion = conectar_bd("EDDO")
    if not conexion: return jsonify({"estatus": False, "error": "Sin conexión EDDO"}), 500
    
    respuesta = registrarDoc(conexion, datos["ID_EMPLEADO"], datos["NOMBRE"], datos["APELLIDO_PAT"], datos["APELLIDO_MAT"], datos["CAMPUS"], correo, datos["TELEFONO"], contra)
    conexion.close()

    llenadoDocumentos(correo) # Llenar docs base

    if respuesta["estatus"]: return jsonify({"estatus": True, "cuenta": respuesta})
    return jsonify({"estatus": False, "error": respuesta["error"]}), 404 
    
def llenadoDocumentos(correo):
    try:
        conexion1 = conectar_bd("BDTEC")
        if not conexion1: return
        datos = traerDocumentosTEC(conexion1,correo)
        conexion1.close()

        conexion = conectar_bd("EDDO")
        if not conexion: return
        for doc in datos: llenadoDoc(conexion,correo,doc["NOMBRE"])
        conexion.close()
    except Exception as e: print("Error llenado:", e)

@app.route("/cuenta", methods=["POST"])
def cuenta():
    data = request.get_json()
    idUsuario = data.get("idUsuario")
    conexion = conectar_bd("BDTEC")
    if not conexion: return jsonify({"estatus": False}), 500
    cuenta = traerEmpleados(conexion, "", idUsuario)
    conexion.close()
    if cuenta: return jsonify({"estatus": True, "cuenta": cuenta})
    return jsonify({"estatus": False}), 404 
    
@app.route("/verificarCorreo", methods=["GET"])
def verificarCorreo():
    correo = request.args.get("correo")
    conexion = conectar_bd("EDDO")
    if not conexion: return jsonify({"estatus": False}), 500
    cursor = conexion.cursor()
    cursor.execute("SELECT COUNT(*) FROM Docente WHERE correo = ?", (correo,))
    resultado = cursor.fetchone()
    conexion.close()
    if resultado and resultado[0] > 0: return jsonify({"estatus": True})
    return jsonify({"estatus": False})

@app.route("/cambiar-contrasena", methods=["POST"])
def cambiarContrasena():
    data = request.get_json()
    conexion = conectar_bd("EDDO")
    if not conexion: return jsonify(False), 500
    cuenta = cambiarContra(conexion, data.get("correo"), data.get("contraNueva"))
    conexion.close()
    return jsonify(True) if cuenta else jsonify(False), 404 
    
@app.route("/cambiarContraActual", methods=["POST"])
def cambiarContraseñaActual():
    data = request.get_json()
    conexion = conectar_bd("EDDO")
    if not conexion: return jsonify({"estatus": False}), 500
    respuesta = cambiarContraActual(conexion, data.get("idUsuario"), data.get("contraActual"), data.get("contraNueva"))
    conexion.close()
    if respuesta["estatus"]: return jsonify({"estatus": True})
    return jsonify({"estatus": False, "error": respuesta["error"]}), 401
    
@app.route("/guardar-mensaje", methods=["POST"])
def guardarMsj():
    data = request.get_json()
    conexion = conectar_bd("EDDO")
    if not conexion: return jsonify({"estatus": False}), 500
    respusta = guardarMensaje(conexion, data.get("idUsuario"), data.get("idReclamo"), data.get("mensaje"), data.get("nombreDoc"))
    conexion.close()
    if respusta: return jsonify({"estatus": True})
    return jsonify({"estatus": False}), 500
    
@app.route("/traer-mensajes", methods=["POST"])
def traerMensajes():
    data = request.get_json()
    try:
        conexion = conectar_bd("EDDO")
        if not conexion: return jsonify({"error": "No conexión"}), 500
        filas = traerMsjs(conexion, data.get("nombreDoc"), data.get("idUsuario"), data.get("documentoSeleccionado")) # Ojo con el orden de params
        
        mensajes = []
        if filas:
            for fila in filas:
                mensajes.append({
                    "remitente": fila[0],
                    "fecha": fila[1].strftime("%Y-%m-%d %H:%M:%S"),
                    "descripcion": fila[2],
                    "nombreDoc": fila[3] 
                })
        return jsonify({"estatus":True,"msjs":mensajes})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/validarRequisito", methods=["POST"])
def validarRequisitos():
    # Nota: Esta ruta usa BDEDD para requisitos documentales
    data = request.get_json()
    idUsuario = data.get("idUsuario")
    conexion = conectar_bd("BDEDD") # Si usas BDEDD aquí
    if not conexion: return jsonify({"estatus": False}), 500
    cumple = validarRequisito(conexion, idUsuario)
    
    # Doble check de plaza aquí también si gustas
    conexion2 = conectar_bd("BDTEC")
    if conexion2:
        plaza = traerPlaza(conexion2, idUsuario)
        if "Tiempo Completo" not in str(plaza): cumple = False
        conexion2.close()
    conexion.close()
    return jsonify({"estatus": True, "cumpleRequisito": cumple})

@app.route('/traerDepartamentos', methods=['GET'])
def traerDepartamentos():
    try:
        conexion = conectar_bd("EDDO")
        if not conexion: return jsonify({"estatus": False}), 500
        cursor = conexion.cursor()
        cursor.execute("SELECT NOMBRE FROM DEPARTAMENTO")
        filas = cursor.fetchall()
        conexion.close()
        departamentos = [{"NOMBRE": f[0]} for f in filas]
        return jsonify({"estatus": True, "departamentos": departamentos})
    except: return []

# --- 5. GENERACIÓN DE CONSTANCIAS ---

@app.route('/generar-constancia', methods=['POST'])
def generar():
    data = request.get_json()
    nombreDoc = data.get("nombreDoc")
    idUsuario = data.get("idUsuario")

    print(f"🔍 BUSCANDO: Doc='{nombreDoc}' | Usuario={idUsuario}")
    
    conexion = conectar_bd("BDTEC")
    if not conexion: return jsonify({"estatus": False, "error": "Sin conexión BDTEC"}), 500

    cursor = conexion.cursor()
    # Query que une Empleado -> EmpleadosXDocumento -> Documento
    query = """
        SELECT ed.DATOS_JSON
        FROM EMPLEADO e
        INNER JOIN EMPLEADOSXDOCUMENTO ed ON e.ID_EMPLEADO = ed.ID_EMPLEADO
        INNER JOIN DOCUMENTO d ON d.ID_DOCUMENTO = ed.ID_DOCUMENTO
        WHERE d.NOMBRE = ? AND e.ID_EMPLEADO = ?
    """
    cursor.execute(query, (nombreDoc, idUsuario))
    row = cursor.fetchone()
    conexion.close()

    if row:
        datos_json = row[0]
        try:
            datos = json.loads(datos_json)
        except:
            return jsonify({"estatus": False, "error": "JSON corrupto"}), 500
            
        # Llamar al conversor con las rutas dinámicas
        path_pdf = generar_constancia(datos, nombreDoc, idUsuario, CARPETA_DOCUMENTOS, CARPETA_FIRMAS)

        if path_pdf and os.path.exists(path_pdf):
            return send_file(path_pdf, mimetype="application/pdf")
        return jsonify({"estatus": False, "error": "Error generando PDF"}), 500
    else:
        return jsonify({"estatus": False, "error": "No hay datos guardados para este documento"}), 404

# --- RUTAS DE GESTIÓN DE DOCUMENTOS (CRUD JSON) ---

@app.route('/traerIdDoce', methods=['GET'])
def traerIdDoce():
    conexion = conectar_bd("BDTEC")
    if not conexion: return jsonify({"estatus": False}), 500
    cursor = conexion.cursor()
    cursor.execute("SELECT ID_EMPLEADO, NOMBRE, APELLIDO_PAT, APELLIDO_MAT FROM empleado")
    filas = cursor.fetchall()
    conexion.close()
    docentes = [{"ID_EMPLEADO": f[0], "NOMBRE": f"{f[1]} {f[2]} {f[3]}"} for f in filas]
    return jsonify({"estatus": True, "docentes": docentes})

@app.route('/traerDocumentos', methods=['POST'])
def traerDocumentos():
    data = request.get_json()
    conexion = conectar_bd("BDTEC")
    if not conexion: return jsonify({"estatus": False}), 500
    cursor = conexion.cursor()
    cursor.execute("""SELECT D.ID_DOCUMENTO, D.NOMBRE FROM DOCUMENTO D
                    INNER JOIN EMPLEADOSXDOCUMENTO ED ON ED.ID_DOCUMENTO = D.ID_DOCUMENTO
                    WHERE ED.ID_EMPLEADO = ?""", (data.get("idDocente"),))
    filas = cursor.fetchall()
    conexion.close()
    docs = [{"ID_DOCUMENTO": f[0], "NOMBRE": f[1]} for f in filas]
    return jsonify({"estatus": True, "documentos": docs})

@app.route('/traerDocumentoLlenado', methods=['GET'])
def traerDocumentoLlenado():
    conexion = conectar_bd("BDTEC")
    if not conexion: return jsonify({"estatus": False}), 500
    cursor = conexion.cursor()
    cursor.execute("SELECT ID_DOCUMENTO, NOMBRE FROM DOCUMENTO")
    filas = cursor.fetchall()
    conexion.close()
    docs = [{"ID_DOCUMENTO": f[0], "NOMBRE": f[1]} for f in filas]
    return jsonify({"estatus": True, "datos_json": docs})

@app.route('/traerDocumento', methods=['POST'])
def traerDocumento():
    data = request.get_json()
    conexion = conectar_bd("BDTEC")
    if not conexion: return jsonify({"estatus": False}), 500
    cursor = conexion.cursor()
    cursor.execute("SELECT DATOS_JSON FROM EMPLEADOSXDOCUMENTO WHERE ID_DOCUMENTO = ? and ID_EMPLEADO = ?", 
                   (data.get('idDocumento'), data.get('idDocente')))
    fila = cursor.fetchone()
    conexion.close()
    if fila: return jsonify({"estatus": True, "datos_json": fila[0]})
    return jsonify({"estatus": False, "error": "No encontrado"}), 404

@app.route('/actualizarDocumentos', methods=['POST'])
def actualizarDocumentos():
    try:
        data = request.get_json()
        conexion = conectar_bd("BDTEC")
        if not conexion: return jsonify({"estatus": False}), 500
        cursor = conexion.cursor()
        cursor.execute("UPDATE EMPLEADOSXDOCUMENTO SET DATOS_JSON = ? WHERE ID_EMPLEADO = ? AND ID_DOCUMENTO = ?", 
                       (json.dumps(data.get("datosJson")), data.get("idEmpleado"), data.get("idDocumento")))
        conexion.commit()
        conexion.close()
        return jsonify({"estatus": True})
    except Exception as e: return jsonify({"estatus": False, "error": str(e)}), 500

@app.route('/insertarDocumento', methods=['POST']) 
def insertarDocumento():
    try:
        data = request.get_json()
        conexion = conectar_bd("BDTEC")
        if not conexion: return {"estatus": False}
        cursor = conexion.cursor()
        
        # Verificar duplicados
        cursor.execute("SELECT COUNT(*) FROM EMPLEADOSXDOCUMENTO WHERE ID_EMPLEADO = ? AND ID_DOCUMENTO = ?", 
                       (data.get("idEmpleado"), data.get("idDocumento")))
        if cursor.fetchone()[0] > 0:
            conexion.close(); return {"estatus": False, "error": "Ya existe"}

        # Insertar
        cursor.execute("INSERT INTO EMPLEADOSXDOCUMENTO (ID_EMPLEADO, ID_DOCUMENTO, DATOS_JSON) VALUES (?, ?, ?)", 
                       (data.get("idEmpleado"), data.get("idDocumento"), json.dumps(data.get("datosJson"))))
        
        # Obtener nombre para llenar en EDDO
        cursor.execute("SELECT NOMBRE FROM DOCUMENTO WHERE ID_DOCUMENTO = ?", (data.get("idDocumento"),))
        nombreDoc = cursor.fetchone()[0]
        conexion.commit()
        conexion.close()

        # Registrar también en EDDO (tabla de seguimiento)
        conexion = conectar_bd("EDDO")
        if conexion:
            cursor = conexion.cursor()
            cursor.execute("SELECT CORREO FROM DOCENTE WHERE ID_DOCENTE = ?", (data.get("idEmpleado"),))
            correo = cursor.fetchone()[0]
            llenadoDoc(conexion, correo, nombreDoc)
            conexion.close()
            
        return {"estatus": True}
    except Exception as e: return {"estatus": False, "error": str(e)}

@app.route('/traerDatosDocumento', methods=['POST'])
def traerDatosDocumento():
    try:
        data = request.get_json()
        conexion = conectar_bd("BDTEC")
        if not conexion: return jsonify({"estatus": False}), 500
        cursor = conexion.cursor()
        cursor.execute("SELECT DATOS_JSON FROM DOCUMENTO WHERE ID_DOCUMENTO = ?", (data.get("idDocumento"),))
        fila = cursor.fetchone()
        conexion.close()
        if fila: return jsonify({"estatus": True, "datos_json": fila[0]})
        return jsonify({"estatus": False, "error": "No encontrado"}), 404
    except Exception as e: return jsonify({"estatus": False, "error": str(e)}), 500

# --- VALIDACIÓN DE ESTADO (BLOQUEO DE ACCIONES) ---

@app.route('/verificar-estado', methods=['POST'])
def verificar_estado():
    data = request.get_json()
    idUsuario = data.get("idUsuario")
    
    # Respuesta por defecto: Todo bien
    respuesta = {
        "bloqueado": False,
        "mensaje": "Bienvenido",
        "color": "black" 
    }

    # 1. ¿Es un docente? (Si es Jefe, no aplicamos restricciones)
    conexion_eddo = conectar_bd("EDDO")
    if not conexion_eddo: return jsonify({"error": "Error EDDO"}), 500
    
    cursor = conexion_eddo.cursor()
    cursor.execute("SELECT CORREO FROM DOCENTE WHERE ID_DOCENTE = ?", (idUsuario,))
    row_docente = cursor.fetchone()
    conexion_eddo.close()

    if not row_docente:
        # Si no está en tabla DOCENTE, asumimos que es Jefe y no lo bloqueamos
        return jsonify(respuesta)
    
    correo_docente = row_docente[0]

    # 2. VALIDAR PLAZA (BDTEC)
    conexion_tec = conectar_bd("BDTEC")
    if conexion_tec:
        cursor = conexion_tec.cursor()
        cursor.execute("""
            SELECT P.HORARIO 
            FROM EMPLEADO E 
            INNER JOIN PLAZA P ON E.ID_PLAZA = P.ID_PLAZA 
            WHERE E.CORREO = ?""", (correo_docente,))
        row_tec = cursor.fetchone()
        conexion_tec.close()

        if row_tec:
            horario = row_tec[0]
            if "Tiempo Completo" not in str(horario):
                return jsonify({
                    "bloqueado": True,
                    "mensaje": f"ACCESO LIMITADO: Tu plaza '{horario}' no cumple con el requisito 'Tiempo Completo'.",
                    "color": "#e74c3c" 
                })
        else:
            return jsonify({
                "bloqueado": True,
                "mensaje": "ACCESO LIMITADO: No se encontró registro de empleado activo en el TEC.",
                "color": "#e74c3c"
            })

    # 3. VALIDAR REQUISITOS DE INICIO (BDEDD)
    conexion_edd = conectar_bd("BDEDD")
    if conexion_edd:
        cursor = conexion_edd.cursor()
        
        # A. Contamos cuántos requisitos pide la convocatoria actual (ID 1)
        cursor.execute("SELECT COUNT(*) FROM REQUISITO_CONVO WHERE ID_CONVOCATORIA = 1")
        total_necesarios = cursor.fetchone()[0]

        # B. Contamos cuántos ha subido el docente
        cursor.execute("SELECT COUNT(*) FROM DOCENTE_REQUISITOS WHERE ID_DOCENTE = ? AND ID_CONVOCATORIA = 1", (idUsuario,))
        total_subidos = cursor.fetchone()[0]
        
        conexion_edd.close()

        # Si tiene menos de los necesarios
        if total_subidos < total_necesarios:
             return jsonify({
                "bloqueado": True,
                "mensaje": f"NO CUMPLES CON LOS REQUISITOS DE INICIO ({total_subidos}/{total_necesarios} entregados).",
                "color": "#e74c3c" 
            })

    return jsonify(respuesta)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)