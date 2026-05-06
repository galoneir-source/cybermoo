#!/usr/bin/env python3
"""
resumen_conexiones.py — Tendencias de jugadores conectados en cyberlife.es

Uso:
    python3 resumen_conexiones.py [-d DIAS]

Por defecto muestra los últimos 30 días.
"""

import argparse
import csv
import os
import signal
from collections import defaultdict
from datetime import datetime, timedelta
from moo_constants import CSV_FILE

_GLOBAL_TIMEOUT = 120

def _timeout_handler(signum, frame):
    raise SystemExit("[ERROR] Timeout global alcanzado ({}s). El script tardó demasiado.".format(_GLOBAL_TIMEOUT))


# Retención del CSV de conexiones; debe coincidir con RETENTION_DAYS en registrar_conexiones.py.
# Independiente de RETENTION_DAYS en auto_backup.sh, que controla los backups de la BD (30 días).
_CSV_RETENTION_DIAS = 90


def cargar_datos():
    if not os.path.exists(CSV_FILE):
        raise FileNotFoundError(f"No se encuentra el CSV de conexiones: {CSV_FILE}")
    registros = []
    omitidas = 0
    with open(CSV_FILE, newline='') as f:
        reader = csv.DictReader(f)
        for fila in reader:
            try:
                ts = datetime.strptime(fila['timestamp'], '%Y-%m-%d %H:%M:%S')
                jugadores = int(fila['jugadores'])
                registros.append((ts, jugadores))
            except (ValueError, IndexError, KeyError):
                omitidas += 1
    if omitidas:
        print(f"[WARN] {omitidas} fila(s) omitidas por formato incorrecto en {CSV_FILE}")
    if registros:
        span = (max(ts for ts, _ in registros) - min(ts for ts, _ in registros)).days + 1
        if span > _CSV_RETENTION_DIAS * 1.1:
            print(f"[WARN] CSV cubre {span} días (retención esperada ≤{_CSV_RETENTION_DIAS}). ¿Falló la purga en registrar_conexiones.py?")
    return registros


def resumen_diario(registros):
    por_dia = defaultdict(list)
    for ts, j in registros:
        por_dia[ts.date()].append(j)
    return {d: vals for d, vals in sorted(por_dia.items())}


def resumen_por_hora(registros):
    por_hora = defaultdict(list)
    for ts, j in registros:
        por_hora[ts.hour].append(j)
    return por_hora


def barra(valor, maximo, ancho=30):
    if maximo == 0:
        return ""
    relleno = round(valor / maximo * ancho)
    return "█" * relleno + "░" * (ancho - relleno)


def main():
    parser = argparse.ArgumentParser(description="Resumen de conexiones al MOO")
    parser.add_argument("-d", "--dias", type=int, default=30,
                        help="Número de días a analizar (por defecto: 30)")
    args = parser.parse_args()

    if not os.path.exists(CSV_FILE):
        print(f"[ERROR] No se encuentra {CSV_FILE}")
        return

    # Carga única: ambos períodos se acotan sobre los mismos datos en memoria.
    # El período anterior cubre exactamente los mismos días que el actual.
    ahora = datetime.now()
    limite_actual = ahora - timedelta(days=args.dias)
    limite_previo = limite_actual - timedelta(days=args.dias)
    todos_registros = cargar_datos()
    registros = [(ts, j) for ts, j in todos_registros if ts >= limite_actual]
    registros_previo = [(ts, j) for ts, j in todos_registros if limite_previo <= ts < limite_actual]

    if not registros:
        print("No hay datos en el período indicado.")
        raise SystemExit(2)

    total = len(registros)
    todos_jugadores = [j for _, j in registros]
    media_global = sum(todos_jugadores) / total
    pico_global = max(todos_jugadores)
    con_jugadores = sum(1 for j in todos_jugadores if j > 0)

    if pico_global == 0:
        print("Sin actividad en el período indicado (0 jugadores en todos los registros).")
        raise SystemExit(2)

    # Tendencia: comparar media del período actual con el período anterior
    if registros_previo:
        media_previo = sum(j for _, j in registros_previo) / len(registros_previo)
        diff = media_global - media_previo
        if diff > 0.1:
            tendencia = f"↑ +{diff:.2f} vs período anterior"
        elif diff < -0.1:
            tendencia = f"↓ {diff:.2f} vs período anterior"
        else:
            tendencia = f"→ estable vs período anterior"
    else:
        tendencia = "sin datos del período anterior"

    dias_con_datos = len({ts.date() for ts, _ in registros})
    dias_esperados = args.dias
    dias_sin_datos = dias_esperados - dias_con_datos

    try:
        tz_nombre = datetime.now().astimezone().strftime("%Z (UTC%z)")
        if not tz_nombre.strip():
            raise ValueError("zona horaria vacía")
    except Exception:
        try:
            with open("/etc/timezone") as _f:
                tz_nombre = _f.read().strip()
        except OSError:
            tz_nombre = "UTC (zona no configurada)"

    print(f"\n{'═' * 54}")
    print(f"  RESUMEN DE CONEXIONES — últimos {args.dias} días")
    print(f"  cyberlife.es:7777  —  hora local: {tz_nombre}")
    print(f"{'═' * 54}")
    print(f"  Filas totales en CSV : {len(todos_registros)}")
    print(f"  Registros analizados : {total}")
    por_dia = resumen_diario(registros)
    dias_parciales = sum(1 for v in por_dia.values() if len(v) < 48)

    print(f"  Días con datos       : {dias_con_datos}/{dias_esperados}"
          + (f" ({dias_sin_datos} sin datos)" if dias_sin_datos > 0 else ""))
    if dias_parciales:
        print(f"  Días parciales (<48) : {dias_parciales} (medias pueden estar sesgadas)")
    print(f"  Media global         : {media_global:.2f} jugadores")
    print(f"  Pico máximo          : {pico_global} jugadores")
    print(f"  Con actividad (>0)   : {con_jugadores}/{total} ({con_jugadores/total*100:.0f}%)")
    print(f"  Tendencia            : {tendencia}")

    # Resumen diario
    print(f"\n{'─' * 54}")
    print("  ACTIVIDAD DIARIA  (media · máx)  ~ = día parcial")
    print(f"{'─' * 54}")
    for dia, vals in por_dia.items():
        media = sum(vals) / len(vals)
        maximo = max(vals)
        b = barra(media, pico_global)
        parcial = "~" if len(vals) < 48 else " "
        print(f"  {dia}  {b}  {media:.1f} · {maximo}  ({len(vals)} reg.){parcial}")

    # Top 5 días más activos (por media sostenida)
    dias_ordenados = sorted(por_dia.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True)[:5]
    print(f"\n{'─' * 54}")
    print("  TOP 5 DÍAS MÁS ACTIVOS  (por media sostenida)")
    print(f"{'─' * 54}")
    for dia, vals in dias_ordenados:
        print(f"  {dia}  media {sum(vals)/len(vals):.1f}  máx {max(vals):2d}")

    # Distribución por hora
    por_hora = resumen_por_hora(registros)
    medias_hora = {h: sum(v) / len(v) for h, v in por_hora.items()}
    max_hora = max(medias_hora.values()) if medias_hora else 0
    hora_pico = max(medias_hora, key=medias_hora.get) if medias_hora else None
    print(f"\n{'─' * 54}")
    print("  ACTIVIDAD POR HORA (media de jugadores)")
    print(f"{'─' * 54}")
    for hora in range(24):
        if hora not in por_hora:
            print(f"  {hora:02d}h  {'░' * 20}  --")
            continue
        vals = por_hora[hora]
        media = sum(vals) / len(vals)
        b = barra(media, max_hora)
        marca = " ◀ pico" if hora == hora_pico else ""
        print(f"  {hora:02d}h  {b}  {media:.2f}{marca}")

    if hora_pico is not None:
        hora_fin = (hora_pico + 1) % 24
        print(f"\n  Franja de mayor actividad: {hora_pico:02d}:00 – {hora_fin:02d}:00  "
              f"(media {medias_hora[hora_pico]:.2f} jugadores)")

    print(f"\n{'═' * 54}\n")

    if hora_pico is not None:
        print(f"SUBJECT:[cyberlife.es] Resumen semanal — pico {hora_pico:02d}:00, máx {pico_global} jugadores")


if __name__ == "__main__":
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(_GLOBAL_TIMEOUT)
    try:
        main()
    finally:
        signal.alarm(0)
