#!/bin/bash
ENV_FILE="/root/MOO-1.8.1/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "$(date '+%F %T') [ERROR] No se encuentra $ENV_FILE. El script no puede continuar." >&2
    exit 1
fi
set -a
source "$ENV_FILE"
set +a

FAILURE_FILE="/root/MOO-1.8.1/tiempo_failures.count"
THRESHOLD=3
# Repetir la alerta cada REPEAT_EVERY fallos tras superar el threshold (2 ejecuciones = ~1h)
REPEAT_EVERY=2

/usr/bin/python3 /root/MOO-1.8.1/tiempo3.py >> /root/MOO-1.8.1/tiempo.log 2>&1
EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 0 ]; then
    rm -f "$FAILURE_FILE"
else
    count=0
    if [ -f "$FAILURE_FILE" ]; then
        raw=$(cat "$FAILURE_FILE")
        [[ "$raw" =~ ^[0-9]+$ ]] && count="$raw" || count=0
    fi
    count=$((count + 1))
    echo "$count" > "$FAILURE_FILE"

    # Alerta al llegar al threshold y luego cada REPEAT_EVERY fallos adicionales
    if [ "$count" -ge "$THRESHOLD" ] && [ $(( (count - THRESHOLD) % REPEAT_EVERY )) -eq 0 ]; then
        ULTIMAS=$(tail -20 /root/MOO-1.8.1/tiempo.log 2>/dev/null || echo "(log no disponible)")
        printf "El script tiempo3.py ha fallado %d veces consecutivas (cada 30 min).\nEl clima del MOO lleva %d minutos sin actualizarse.\n\n--- Últimas líneas de tiempo.log ---\n%s\n" \
            "$count" "$((count * 30))" "$ULTIMAS" | \
            mail -s "[ALERTA] Clima MOO: $count fallos consecutivos en cyberlife.es" \
                 "$ALERT_EMAIL" 2>/dev/null
    fi
fi

exit "$EXIT_CODE"
