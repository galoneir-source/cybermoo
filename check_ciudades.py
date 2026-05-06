#!/usr/bin/env python3
"""
check_ciudades.py — Smoke-test de las queries de WeatherAPI definidas en ciudades.conf

Uso:
    python3 check_ciudades.py

Comprueba que cada ciudad del fichero de configuración devuelve una respuesta
válida de WeatherAPI. Útil antes de editar ciudades.conf en producción.
Sale con código 0 si todas las ciudades pasan, 1 si alguna falla.
"""

import os
import sys
import time
import requests
from moo_constants import cargar_ciudades, CIUDADES_FILE

# Cargar .env automáticamente para poder ejecutar el script sin wrapper shell
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                _k = _k.strip()
                _v = _v.strip()
                if len(_v) >= 2 and _v[0] in ('"', "'") and _v[-1] == _v[0]:
                    _v = _v[1:-1]
                os.environ.setdefault(_k, _v)

WEATHER_API_KEY = os.environ.get("WEATHERAPI_KEY")
if not WEATHER_API_KEY:
    print(f"[ERROR] Falta la variable de entorno WEATHERAPI_KEY. "
          f"Defínela en el entorno o en {_env_path}")
    sys.exit(1)

try:
    TIMEOUT = int(os.environ.get("WEATHERAPI_TIMEOUT", 10))
except ValueError:
    print(f"[ERROR] WEATHERAPI_TIMEOUT en .env no es un entero válido: {os.environ.get('WEATHERAPI_TIMEOUT')!r}")
    sys.exit(1)


def check_ciudad(nombre, query):
    url = (
        f"https://api.weatherapi.com/v1/forecast.json"
        f"?key={WEATHER_API_KEY}&q={query}&days=1&lang=es"
    )
    t0 = time.monotonic()
    try:
        r = requests.get(url, timeout=TIMEOUT)
        elapsed = round((time.monotonic() - t0) * 1000)
        r.raise_for_status()
        data = r.json()
        temp = round(data["current"]["temp_c"], 1)
        texto = data["current"]["condition"]["text"].strip().capitalize()
        forecastday = data.get("forecast", {}).get("forecastday", [])
        if forecastday:
            dia = forecastday[0].get("day", {})
            raw_min = dia.get("mintemp_c")
            raw_max = dia.get("maxtemp_c")
            if raw_min is not None and raw_max is not None:
                print(f"  [OK]    {nombre:<20} {texto}, {temp}°C (min {round(raw_min,1)}, max {round(raw_max,1)})  ({elapsed}ms)")
                return True
        print(f"  [OK]    {nombre:<20} {texto}, {temp}°C (sin min/max)  ({elapsed}ms)")
        return True
    except requests.HTTPError as e:
        elapsed = round((time.monotonic() - t0) * 1000)
        print(f"  [FAIL]  {nombre:<20} HTTP {e.response.status_code}: {e}  ({elapsed}ms)")
        return False
    except Exception as e:
        elapsed = round((time.monotonic() - t0) * 1000)
        print(f"  [FAIL]  {nombre:<20} {type(e).__name__}: {e}  ({elapsed}ms)")
        return False


def main():
    try:
        ciudades, avisos = cargar_ciudades(CIUDADES_FILE)
    except (SystemExit, ValueError) as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    for aviso in avisos:
        print(f"[WARN] {aviso}")

    print(f"Comprobando {len(ciudades)} ciudad(es) en {CIUDADES_FILE}...\n")
    fallos = 0
    for nombre, query, prop in ciudades:
        if not check_ciudad(nombre, query):
            fallos += 1

    print(f"\n{'─' * 46}")
    if fallos == 0:
        print(f"  Resultado: todas las ciudades OK ({len(ciudades)}/{len(ciudades)})")
        sys.exit(0)
    else:
        print(f"  Resultado: {fallos} ciudad(es) con error ({len(ciudades) - fallos}/{len(ciudades)} OK)")
        sys.exit(1)


if __name__ == "__main__":
    main()
