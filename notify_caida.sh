#!/bin/bash
# Envía alerta por email cuando el servicio LambdaMOO entra en estado fallido.

LOG_FILE="/root/MOO-1.8.1/caidas.log"
RETENTION_DAYS=365

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG_FILE"; }

# Purgar entradas más antiguas que RETENTION_DAYS
if [[ -f "$LOG_FILE" ]]; then
    CUTOFF=$(date -d "-${RETENTION_DAYS} days" '+%Y-%m-%d')
    TMP="${LOG_FILE}.tmp"
    grep -v '^\.' "$LOG_FILE" | awk -v cutoff="$CUTOFF" '$1 >= cutoff' > "$TMP" && mv "$TMP" "$LOG_FILE" || rm -f "$TMP"
fi

ENV_FILE="/root/MOO-1.8.1/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    log "[ERROR] No se encuentra $ENV_FILE. No se puede enviar la alerta."
    exit 1
fi
source "$ENV_FILE"
DEST="${ALERT_EMAIL:?Variable ALERT_EMAIL no definida en .env}"
HOST="$(hostname -f 2>/dev/null || hostname)"
FECHA="$(date '+%Y-%m-%d %H:%M:%S')"

SUBJECT="[ALERTA] LambdaMOO caído en $HOST"

BODY="El servicio LambdaMOO (cyberlife.es) ha fallado y systemd no pudo reiniciarlo automáticamente.

Fecha/hora : $FECHA
Servidor   : $HOST
Puerto     : 7777

Últimas líneas del log:
$(journalctl -u lambdamoo.service -n 30 --no-pager 2>/dev/null)

---
Para reiniciar manualmente:
  systemctl start lambdamoo.service

Para ver el estado:
  systemctl status lambdamoo.service
"

log "[CAÍDA] Servicio LambdaMOO caído. Enviando alerta a $DEST."
if echo "$BODY" | mail -s "$SUBJECT" "$DEST"; then
    log "[OK] Alerta enviada correctamente."
else
    log "[ERROR] Fallo al enviar la alerta por email."
fi
