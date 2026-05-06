import signal
import socket
import re
from datetime import datetime, timedelta
import csv
import os
from moo_constants import CSV_FILE, leer_hasta

# Timeout global: aborta si el script tarda más de 10 min (cron cada 15 min)
_GLOBAL_TIMEOUT = 600

def _timeout_handler(signum, frame):
    raise SystemExit("[ERROR] Timeout global alcanzado ({}s). El script tardó demasiado.".format(_GLOBAL_TIMEOUT))

# Configuración — servidor
HOST = os.environ.get("MOO_HOST", "cyberlife.es")
try:
    PORT           = int(os.environ.get("MOO_PORT", 7777))
    CONNECT_TIMEOUT = int(os.environ.get("MOO_CONNECT_TIMEOUT", 15))
    READ_TIMEOUT    = int(os.environ.get("MOO_READ_TIMEOUT", 15))
except ValueError as e:
    raise SystemExit(f"[ERROR] Variable de entorno numérica inválida en .env: {e}")

# Configuración — CSV
RETENTION_DAYS = 90
try:
    MAX_JUGADORES = int(os.environ.get("MAX_JUGADORES", 500))
except ValueError:
    raise SystemExit(f"[ERROR] MAX_JUGADORES en .env no es un entero válido: {os.environ.get('MAX_JUGADORES')!r}")
CABECERA = ['timestamp', 'jugadores']



def obtener_jugadores_conectados():
    try:
        with socket.create_connection((HOST, PORT), timeout=CONNECT_TIMEOUT) as sock:
            sock.sendall(b"WHO\n")
            datos, _ = leer_hasta(sock, b"Jugadores conectados", timeout=READ_TIMEOUT)
            salida = datos.decode('utf-8', errors='replace')

        match = re.search(r'Jugadores conectados:\s*(\d+)', salida)
        if match:
            return int(match.group(1))
        else:
            print(f"[WARN] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} No se encontró el número de jugadores en la respuesta.")
            return None
    except Exception as e:
        print(f"[ERROR] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {type(e).__name__}: {e}")
        return None


def purgar_entradas_antiguas():
    if not os.path.exists(CSV_FILE):
        print("[INFO] CSV no existe aún, primera ejecución.")
        return
    limite = datetime.now() - timedelta(days=RETENTION_DAYS)

    # Comprobación rápida: busca la primera fila con timestamp válido (la más
    # antigua). Si está dentro del período de retención, nada necesita purgarse.
    # Las filas inválidas se saltan; si no hay ninguna válida, cae al scan completo.
    with open(CSV_FILE, newline='') as f:
        reader = csv.DictReader(f)
        cabecera_real = list(reader.fieldnames or [])
        if not cabecera_real:
            return  # Fichero vacío: nada que purgar
        if cabecera_real != CABECERA:
            print(f"[WARN] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                  f"Cabecera del CSV inesperada: {cabecera_real} (esperada: {CABECERA}). "
                  f"¿Se añadió una columna sin migrar el fichero?")
        for fila in reader:
            try:
                if datetime.strptime(fila['timestamp'], '%Y-%m-%d %H:%M:%S') >= limite:
                    return  # La entrada más antigua válida está dentro del período
                break       # Fuera del período: necesita scan completo
            except (ValueError, KeyError):
                continue

    filas_validas = []
    eliminadas = 0
    with open(CSV_FILE, newline='') as f:
        reader = csv.DictReader(f)
        for fila in reader:
            try:
                ts = datetime.strptime(fila['timestamp'], '%Y-%m-%d %H:%M:%S')
                if ts >= limite:
                    filas_validas.append(fila)
                else:
                    eliminadas += 1
            except (ValueError, KeyError):
                filas_validas.append(fila)
    if eliminadas:
        tmp = CSV_FILE + ".tmp"
        with open(tmp, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CABECERA)
            writer.writeheader()
            writer.writerows(filas_validas)
        os.replace(tmp, CSV_FILE)
        print(f"Purgadas {eliminadas} entradas con más de {RETENTION_DAYS} días. Quedan {len(filas_validas)}.")


def registrar_conexion():
    jugadores = obtener_jugadores_conectados()
    if jugadores is None:
        raise SystemExit(1)
    if jugadores < 0:
        print(f"[ERROR] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Número de jugadores negativo ({jugadores}). Registro cancelado.")
        raise SystemExit(1)
    if jugadores > MAX_JUGADORES:
        print(f"[WARN] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Número de jugadores inusualmente alto ({jugadores} > {MAX_JUGADORES}). Registrando de todas formas.")
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    es_nuevo = not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0
    with open(CSV_FILE, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        if es_nuevo:
            writer.writerow(CABECERA)
        writer.writerow([timestamp, jugadores])
    print(f"Registrado: {timestamp} - {jugadores} jugadores")


if __name__ == "__main__":
    _t0 = datetime.now()
    print(f"[START] {_t0.strftime('%Y-%m-%d %H:%M:%S')} registrar_conexiones.py")
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(_GLOBAL_TIMEOUT)
    try:
        purgar_entradas_antiguas()
        registrar_conexion()
        _dur = (datetime.now() - _t0).seconds
        print(f"[END] OK — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({_dur}s)")
    finally:
        signal.alarm(0)
