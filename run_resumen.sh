#!/bin/bash
ENV_FILE="/root/MOO-1.8.1/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "$(date '+%F %T') [ERROR] No se encuentra $ENV_FILE. El script no puede continuar." >&2
    exit 1
fi
set -a
source "$ENV_FILE"
set +a

LOG_FILE="/root/MOO-1.8.1/registrar.log"

REPORTE=$(/usr/bin/python3 /root/MOO-1.8.1/resumen_conexiones.py -d 7 2>&1)
EXIT_CODE=$?
echo "$REPORTE" >> "$LOG_FILE"

# Código 2: sin datos o sin actividad — no enviar email pero sí registrar
if [ "$EXIT_CODE" -eq 2 ]; then
    echo "$(date '+%F %T') [INFO] Resumen semanal suprimido: sin actividad en los últimos 7 días." | tee -a "$LOG_FILE"
    exit 0
fi

# Cualquier otro código de error — alertar
if [ "$EXIT_CODE" -ne 0 ]; then
    echo "$(date '+%F %T') [ERROR] resumen_conexiones.py falló con código $EXIT_CODE." | tee -a "$LOG_FILE"
    ULTIMAS=$(tail -20 "$LOG_FILE" 2>/dev/null || echo "(log no disponible)")
    printf "resumen_conexiones.py falló con código %d.\n\n--- Últimas líneas de registrar.log ---\n%s\n" \
        "$EXIT_CODE" "$ULTIMAS" | \
        mail -s "[ERROR] Resumen MOO: fallo inesperado (código $EXIT_CODE)" "$ALERT_EMAIL" 2>/dev/null || true
    exit 1
fi

# Extraer asunto dinámico y eliminar la línea SUBJECT: del cuerpo
SUBJECT=$(echo "$REPORTE" | grep '^SUBJECT:' | sed 's/^SUBJECT://')
CUERPO=$(echo "$REPORTE" | grep -v '^SUBJECT:')

if [[ -z "$SUBJECT" ]]; then
    SUBJECT="[cyberlife.es] Resumen semanal de conexiones"
fi

echo "$CUERPO" | mail -s "$SUBJECT" "$ALERT_EMAIL" 2>/dev/null
