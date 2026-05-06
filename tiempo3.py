import os
import signal
import socket
import time
import requests
from moo_constants import leer_hasta, cargar_ciudades, CIUDADES_FILE

# Timeout global: aborta si el script tarda más de 20 min (cron cada 30 min)
_GLOBAL_TIMEOUT = 1200

def _timeout_handler(signum, frame):
    raise SystemExit("[ERROR] Timeout global alcanzado ({}s). El script tardó demasiado.".format(_GLOBAL_TIMEOUT))

WEATHER_API_KEY = os.environ.get("WEATHERAPI_KEY")
if not WEATHER_API_KEY:
    raise EnvironmentError("Falta la variable de entorno WEATHERAPI_KEY")

HOST = os.environ.get("MOO_HOST", "cyberlife.es")
MOO_BOT_USER = os.environ.get("MOO_BOT_USER")
MOO_BOT_PASSWORD = os.environ.get("MOO_BOT_PASSWORD")
if not MOO_BOT_USER or not MOO_BOT_PASSWORD:
    raise EnvironmentError("Faltan las variables de entorno MOO_BOT_USER y/o MOO_BOT_PASSWORD")
try:
    PORT               = int(os.environ.get("MOO_PORT", 7777))
    WEATHERAPI_TIMEOUT = int(os.environ.get("WEATHERAPI_TIMEOUT", 10))
except ValueError as e:
    raise SystemExit(f"[ERROR] Variable de entorno numérica inválida en .env: {e}")
COMANDO = "tiempolog"

def obtener_clima(query, reintentos=2, espera=5):
    url = (
        f"https://api.weatherapi.com/v1/forecast.json"
        f"?key={WEATHER_API_KEY}&q={query}&days=1&lang=es"
    )
    ultimo_error: Exception = RuntimeError(f"Sin intentos disponibles para '{query}'")
    for intento in range(1 + reintentos):
        try:
            _t = time.monotonic()
            response = requests.get(url, timeout=WEATHERAPI_TIMEOUT)
            elapsed_ms = round((time.monotonic() - _t) * 1000)
            response.raise_for_status()
            data = response.json()
            texto = data["current"]["condition"]["text"].strip().capitalize()
            temp = round(data["current"]["temp_c"], 1)
            resultado = f"El clima actual es {texto} y la temperatura es {temp} grados Celsius."
            forecastdays = data.get("forecast", {}).get("forecastday", [])
            if forecastdays:
                dia = forecastdays[0].get("day", {})
                raw_min = dia.get("mintemp_c")
                raw_max = dia.get("maxtemp_c")
                if raw_min is not None and raw_max is not None:
                    resultado = (f"El clima actual es {texto} y la temperatura es {temp} grados Celsius "
                                 f"(min {round(raw_min, 1)}, max {round(raw_max, 1)}).")
            if intento > 0:
                print(f"[WARN] '{query}' recuperado en el intento {intento + 1} (tras {intento} fallo(s)).")
            return resultado, elapsed_ms
        except Exception as e:
            ultimo_error = e
            if intento < reintentos:
                print(f"[WARN] Intento {intento + 1} fallido para '{query}': {e}. Reintentando en {espera}s...")
                time.sleep(espera)
    raise ultimo_error


def main():
    _t0 = time.monotonic()
    print(f"[START] {time.strftime('%Y-%m-%d %H:%M:%S')} tiempo3.py")
    try:
        ciudades, ciudades_avisos = cargar_ciudades(CIUDADES_FILE)
    except (ValueError, SystemExit) as e:
        duracion = round(time.monotonic() - _t0)
        print(f"[ERROR] {e}")
        print(f"[RESUMEN] API: 0/0 ciudades obtenidas | Duración: {duracion}s")
        raise SystemExit(1)
    for aviso in ciudades_avisos:
        print(f"[WARN] {aviso}")
    # Obtener clima de todas las ciudades
    resultados = {}
    for nombre, query, prop in ciudades:
        try:
            resultados[prop], elapsed_ms = obtener_clima(query)
            print(f"[OK] {nombre}: {resultados[prop]}  ({elapsed_ms}ms)")
        except Exception as e:
            print(f"[ERROR] {nombre}: {e}")

    if not resultados:
        duracion = round(time.monotonic() - _t0)
        print("[ERROR] No se obtuvo clima de ninguna ciudad. Abortando conexión al MOO.")
        print(f"[RESUMEN] API: 0/{len(ciudades)} ciudades obtenidas ({len(ciudades)} fallidas) | Duración: {duracion}s")
        raise SystemExit(1)

    print(f"\n[INFO] {len(resultados)}/{len(ciudades)} ciudades obtenidas. Conectando al MOO...")

    # Conectar al MOO y actualizar propiedades
    try:
        with socket.create_connection((HOST, PORT), timeout=15) as sock:
            _, ok = leer_hasta(sock, [b"conectar", b"connect", b"escribe conectar"])
            if not ok:
                raise ConnectionError("No se recibió el prompt de login del MOO.")
            login = f"conectar {MOO_BOT_USER} {MOO_BOT_PASSWORD}"
            sock.sendall(login.encode("utf-8") + b"\n")
            banner_raw, ok = leer_hasta(sock, [b"establecida", b"connected", b"ltima conexi", b"Te encuentras"])
            if not ok:
                raise ConnectionError("No se confirmó la conexión al MOO.")
            # Registrar líneas útiles del banner (última conexión, notificaciones)
            for linea in banner_raw.decode("utf-8", errors="replace").splitlines():
                linea = linea.strip()
                if any(k in linea for k in ("ltima", "notificaci", "cambios", "SOUND")):
                    print(f"[MOO] {linea}")
            sock.sendall(COMANDO.encode("ascii") + b"\n")

            fallos_set = []
            for prop, clima in resultados.items():
                clima_escaped = clima.replace('"', '\\"')
                comando = f'\\@set {prop} to "{clima_escaped}"\n'
                sock.sendall(comando.encode("utf-8"))
                respuesta, _ = leer_hasta(sock, [b"set to", b"ermission", b"no such", b"nknown"], timeout=5)
                texto = respuesta.decode("utf-8", errors="replace")
                ultima_linea = next(
                    (l.strip() for l in reversed(texto.splitlines()) if l.strip()), ""
                )
                if b"set to" in respuesta:
                    print(f"[OK] {prop}: {ultima_linea}")
                else:
                    print(f"[WARN] {prop}: respuesta inesperada: {ultima_linea}")
                    fallos_set.append(prop)

            sock.sendall(b"dormir\n")
            leer_hasta(sock, [b"dormir", b"sleep"], timeout=5)

        exitos = len(resultados) - len(fallos_set)
        total_ciudades = len(ciudades)
        fallos_api = total_ciudades - len(resultados)
        duracion = round(time.monotonic() - _t0)
        print(f"\n[RESUMEN] API: {len(resultados)}/{total_ciudades} ciudades obtenidas"
              + (f" ({fallos_api} fallidas)" if fallos_api else "")
              + f" | MOO: {exitos}/{len(resultados)} propiedades actualizadas"
              + (f" ({len(fallos_set)} no confirmadas)" if fallos_set else "")
              + f" | Duración: {duracion}s")
        if fallos_set:
            print(f"[WARN] Propiedades no confirmadas: {fallos_set}")
            raise SystemExit(1)
        print("[OK] Actualización del MOO completada.")
    except Exception as e:
        print(f"[ERROR] Fallo al conectar o actualizar el MOO: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(_GLOBAL_TIMEOUT)
    try:
        main()
    finally:
        signal.alarm(0)
