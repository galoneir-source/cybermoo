#!/usr/bin/env python3
"""
database_checker.py — Inspecciona zonas problemáticas de una BD LambdaMOO.

Uso:
    python3 database_checker.py -p POSICION [opciones]

Ejemplos:
    python3 database_checker.py -p 29794304
    python3 database_checker.py -p 29794304 -f lambdacore.db.new -r 2000
    python3 database_checker.py -p 29794304 --hex
"""

import argparse
import re
import sys

# Patrones de línea válidos en el formato LambdaMOO DB v4
_VALID_LINE = re.compile(
    r'^('
    r'-?\d+'             # entero (positivo o negativo)
    r'|\d+\.\d+'         # float
    r'|#-?\d+'           # referencia a objeto (#N o #-1)
    r'|\*\*.*'           # cabecera (** LambdaMOO Database... **)
    r'|".*'              # valor string
    r'|\{.*'             # lista
    r'|\[.*'             # waif
    r'|[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+'  # texto libre sin chars de control
    r')$'
)


def _es_linea_anomala(line: str) -> tuple[bool, str]:
    """Devuelve (es_anomala, motivo)."""
    # Caracteres de control (excluye \t, \n, \r que son normales)
    ctrl = [c for c in line if '\x00' <= c <= '\x08' or '\x0b' <= c <= '\x0c'
            or '\x0e' <= c <= '\x1f' or c == '\x7f']
    if ctrl:
        chars = ', '.join(f'0x{ord(c):02x}' for c in set(ctrl))
        return True, f"caracteres de control: {chars}"

    # Alto porcentaje de caracteres no imprimibles (posible binario)
    if len(line) > 4:
        no_print = sum(1 for c in line if not (32 <= ord(c) <= 126 or ord(c) > 127))
        if no_print / len(line) > 0.3:
            return True, f"{no_print}/{len(line)} chars no imprimibles"

    # Línea excesivamente larga (>4096 chars) sin ser código MOO
    if len(line) > 4096 and not line.startswith('"'):
        return True, f"línea anormalmente larga ({len(line)} chars)"

    # No encaja en ningún patrón conocido del formato DB
    if line and not _VALID_LINE.match(line):
        return True, "no coincide con ningún formato DB conocido"

    return False, ""


def check_database(file_path, error_position, range_to_check=1000, show_hex=False):
    try:
        with open(file_path, "rb") as db_file:
            start = max(0, error_position - range_to_check)
            db_file.seek(start)
            data = db_file.read(range_to_check * 2)

        print(f"Archivo  : {file_path}")
        print(f"Posición : {error_position}  (contexto ±{range_to_check} bytes)")
        print(f"Offset   : {start} – {start + len(data)}")
        print()

        if show_hex:
            for i in range(0, len(data), 16):
                chunk = data[i:i + 16]
                hex_part = " ".join(f"{b:02x}" for b in chunk)
                asc_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                abs_offset = start + i
                marker = " <--" if abs_offset <= error_position < abs_offset + 16 else ""
                print(f"{abs_offset:10d}  {hex_part:<47}  {asc_part}{marker}")
        else:
            text = data.decode("latin-1")
            lines = text.splitlines()

            # Calcular offset de byte por línea para marcar la línea del error
            byte_offset = start
            anomalies = 0
            for i, line in enumerate(lines):
                line_start = byte_offset
                byte_offset += len(line.encode("latin-1")) + 1  # +1 por \n

                anomala, motivo = _es_linea_anomala(line)
                cerca_error = line_start <= error_position < byte_offset

                if anomala:
                    marca = " <-- ERROR" if cerca_error else ""
                    print(f"  [ANOMALÍA] Línea {i:4d} (offset {line_start}): {motivo}{marca}")
                    print(f"             {line[:120]!r}")
                    anomalies += 1
                elif cerca_error:
                    print(f"  [POSICIÓN] Línea {i:4d} (offset {line_start}): {line[:120]!r}")

            if anomalies == 0:
                print("  No se detectaron anomalías en el rango indicado.")
            else:
                print(f"\n  Total de anomalías detectadas: {anomalies}")

        print("\nComprobación completada.")

    except FileNotFoundError:
        print(f"[ERROR] Archivo no encontrado: {file_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Inspecciona zonas problemáticas de una base de datos LambdaMOO."
    )
    parser.add_argument(
        "-f", "--file",
        default="/root/MOO-1.8.1/lambdacore.db",
        metavar="ARCHIVO",
        help="Ruta al archivo de BD (por defecto: lambdacore.db)"
    )
    parser.add_argument(
        "-p", "--position",
        type=int,
        required=True,
        metavar="BYTES",
        help="Posición en bytes donde se reportó el error (del log del servidor)"
    )
    parser.add_argument(
        "-r", "--range",
        type=int,
        default=1000,
        metavar="BYTES",
        help="Bytes a leer antes y después de la posición (por defecto: 1000)"
    )
    parser.add_argument(
        "--hex",
        action="store_true",
        help="Mostrar volcado hexadecimal en lugar de análisis de líneas"
    )

    args = parser.parse_args()
    check_database(args.file, args.position, args.range, args.hex)


if __name__ == "__main__":
    main()
