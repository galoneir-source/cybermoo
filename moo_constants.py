import os
import re
import socket

# Constantes internas compartidas entre scripts del proyecto.
MAX_BUFFER = 65536                              # 64 KB — límite del buffer de lectura del socket MOO
CSV_FILE   = "/root/MOO-1.8.1/conexiones.csv"  # CSV de estadísticas de conexión
CIUDADES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ciudades.conf")


def leer_hasta(sock, patrones, timeout=10):
    """Lee del socket hasta encontrar alguno de los patrones, agotar el timeout o superar MAX_BUFFER.

    patrones: bytes o list[bytes]. Cualquier otro tipo lanza TypeError.
    Devuelve (buffer: bytes, encontrado: bool).
    """
    if isinstance(patrones, bytes):
        patrones = [patrones]
    elif not isinstance(patrones, list):
        raise TypeError(f"patrones debe ser bytes o list, no {type(patrones).__name__}")
    sock.settimeout(timeout)
    buffer = b""
    while not any(p in buffer for p in patrones):
        try:
            chunk = sock.recv(1024)
            if not chunk:
                break
            buffer += chunk
            if len(buffer) >= MAX_BUFFER:
                break
        except socket.timeout:
            break
    return buffer, any(p in buffer for p in patrones)


def cargar_ciudades(path):
    """Carga ciudades desde path.

    Devuelve (ciudades, avisos) donde avisos es una lista de strings con
    las líneas ignoradas. El caller decide cómo mostrarlos.
    """
    if not os.path.exists(path):
        raise SystemExit(f"[ERROR] No se encuentra el fichero de ciudades: {path}")
    ciudades = []
    avisos = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for num, linea in enumerate(f, 1):
            if '�' in linea:
                avisos.append(f"Línea {num} de {path} contiene bytes no válidos en UTF-8 (sustituidos). Guarda el fichero como UTF-8.")
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            partes = linea.split("|", 2)
            if len(partes) != 3:
                avisos.append(f"Línea ignorada en {path}: {linea!r}")
                continue
            nombre, query, prop = (p.strip() for p in partes)
            if not re.match(r'^\\[#$][A-Za-z0-9_]+\.[A-Za-z0-9_]+$', prop):
                avisos.append(f"Propiedad MOO inválida en {path}: {prop!r} (línea: {linea!r})")
                continue
            ciudades.append((nombre, query, prop))
    if not ciudades:
        raise ValueError(f"No se encontraron ciudades válidas en {path}")
    return ciudades, avisos
