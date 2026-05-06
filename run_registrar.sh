#!/bin/bash
ENV_FILE="/root/MOO-1.8.1/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "$(date '+%F %T') [ERROR] No se encuentra $ENV_FILE. El script no puede continuar." >&2
    exit 1
fi
set -a
source "$ENV_FILE"
set +a

FAILURE_FILE="/root/MOO-1.8.1/registrar_failures.count"
THRESHOLD=3
# Repetir la alerta cada REPEAT_EVERY fallos tras superar el threshold (2 ejecuciones = ~30min)
REPEAT_EVERY=2

/usr/bin/python3 /root/MOO-1.8.1/registrar_conexiones.py >> /root/MOO-1.8.1/registrar.log 2>&1
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

    if [ "$count" -ge "$THRESHOLD" ] && [ $(( (count - THRESHOLD) % REPEAT_EVERY )) -eq 0 ]; then
        ULTIMAS=$(tail -20 /root/MOO-1.8.1/registrar.log 2>/dev/null || echo "(log no disponible)")
        printf "El script registrar_conexiones.py ha fallado %d veces consecutivas (cada 15 min).\nLas estadísticas llevan %d minutos sin registrarse.\n\n--- Últimas líneas de registrar.log ---\n%s\n" \
            "$count" "$((count * 15))" "$ULTIMAS" | \
            mail -s "[ALERTA] Registro MOO: $count fallos consecutivos en cyberlife.es" \
                 "$ALERT_EMAIL" 2>/dev/null
    fi
fi

# Comprobar en cada ejecución que el backup más reciente no tiene más de 2 días.
# El marcador almacena la fecha del último email enviado para no repetir la alerta
# más de una vez al día. La limpieza del marcador ocurre en cada ejecución (cada
# 15 min) en cuanto el backup vuelve a estar al día, no al día siguiente.
BACKUP_DIR="/root/MOO-1.8.1/backups"
BACKUP_MAX_DAYS=2
BACKUP_ALERT_MARKER="/root/MOO-1.8.1/backup_stale.alert"
HOY=$(date '+%Y-%m-%d')

ULTIMO=$(find "$BACKUP_DIR" -type f -name "lambdacore_*.db.gz" | sort | tail -1)
if [[ -z "$ULTIMO" ]]; then
    if [[ ! -f "$BACKUP_ALERT_MARKER" ]] || [[ "$(cat "$BACKUP_ALERT_MARKER")" != "$HOY" ]]; then
        echo "No se encontró ningún backup en $BACKUP_DIR." \
            | mail -s "[ALERTA] Backup MOO: sin backups en $BACKUP_DIR" "$ALERT_EMAIL" 2>/dev/null
        echo "$HOY" > "$BACKUP_ALERT_MARKER"
    fi
else
    # Extraer YYYYMMDD del nombre sin grep -P (usa expansión de parámetros)
    base="$(basename "$ULTIMO")"          # lambdacore_20260505_0300.db.gz
    base="${base#lambdacore_}"            # 20260505_0300.db.gz
    FILEDATE="${base%%_*}"                # 20260505
    CUTOFF=$(date -d "-${BACKUP_MAX_DAYS} days" '+%Y%m%d')
    if [[ "$FILEDATE" =~ ^[0-9]{8}$ ]] && [[ "$FILEDATE" < "$CUTOFF" ]]; then
        if [[ ! -f "$BACKUP_ALERT_MARKER" ]] || [[ "$(cat "$BACKUP_ALERT_MARKER")" != "$HOY" ]]; then
            echo "El backup más reciente es del $FILEDATE (hace más de $BACKUP_MAX_DAYS días).
Revisa el cron de auto_backup.sh en el servidor." \
                | mail -s "[ALERTA] Backup MOO: último backup desactualizado ($FILEDATE)" "$ALERT_EMAIL" 2>/dev/null
            echo "$HOY" > "$BACKUP_ALERT_MARKER"
        fi
    else
        rm -f "$BACKUP_ALERT_MARKER"
    fi
fi

exit "$EXIT_CODE"
