#!/bin/bash
set -euo pipefail

########## CONFIGURACIÓN ##########
MOO_DIR="/root/MOO-1.8.1"
DB_NAME="lambdacore.db"
BACKUP_DIR="$MOO_DIR/backups"
LOG_FILE="$MOO_DIR/backup.log"
# Días que se conservan los backups de la BD (independiente de la retención del
# CSV de conexiones, que es de 90 días y se gestiona en registrar_conexiones.py)
RETENTION_DAYS=30
# Máximo tiempo de espera (segundos) a que termine un checkpoint en curso
MAX_WAIT=300
###################################

# Cargar ALERT_EMAIL desde .env (misma fuente que el resto de scripts)
if [[ ! -f "$MOO_DIR/.env" ]]; then
    echo "$(date '+%F %T') [ERROR] No se encuentra $MOO_DIR/.env. El script no puede continuar." >&2
    exit 1
fi
# shellcheck source=/root/MOO-1.8.1/.env
source "$MOO_DIR/.env"
ALERT_EMAIL="${ALERT_EMAIL:?Variable ALERT_EMAIL no definida en .env}"

DATE="$(date '+%Y%m%d_%H%M')"
DB="$MOO_DIR/$DB_NAME"
DB_NEW="$MOO_DIR/$DB_NAME.new"
RAW_DEST="$BACKUP_DIR/${DB_NAME%.db}_$DATE.db"
DEST="$RAW_DEST.gz"

log() {
    local level="$1"; shift
    echo "$(date '+%F %T') [$level] $*" | tee -a "$LOG_FILE"
}

mkdir -p "$BACKUP_DIR"
if [[ ! -w "$BACKUP_DIR" ]]; then
    log "ERROR" "Sin permisos de escritura en $BACKUP_DIR"
    echo "El directorio de backups $BACKUP_DIR existe pero no tiene permisos de escritura." \
        | mail -s "[ERROR] Backup MOO: sin permisos en $BACKUP_DIR" "$ALERT_EMAIL" 2>/dev/null || true
    exit 1
fi

# Verificar dependencias necesarias
for cmd in gzip stat df numfmt; do
    if ! command -v "$cmd" &>/dev/null; then
        log "ERROR" "Comando requerido no encontrado: $cmd"
        echo "Comando requerido no encontrado: $cmd. Instálalo antes de ejecutar este script." \
            | mail -s "[ERROR] Backup MOO: dependencia faltante ($cmd)" "$ALERT_EMAIL" 2>/dev/null || true
        exit 1
    fi
done

alert() {
    local subject="$1"
    local body="${2:-$1}"
    local level="${3:-WARN}"
    log "$level" "$subject"
    echo "$body" | mail -s "[AVISO] Backup MOO: $subject" "$ALERT_EMAIL" 2>/dev/null || true
}

checkpoint_activo() {
    find "$(dirname "$DB_NEW")" -maxdepth 1 -name "$(basename "$DB_NEW").#[0-9]*#" -print -quit | grep -q .
}

# Elegir la fuente del backup:
# Preferimos lambdacore.db.new (último checkpoint completo).
# LambdaMOO escribe el checkpoint en lambdacore.db.new.#PID# y al terminar lo
# renombra a lambdacore.db.new; mientras ese archivo temporal exista, hay un
# checkpoint en curso. Esperamos a que desaparezca antes de copiar.
# Si .new no existe o la espera agota, usamos lambdacore.db como fallback.

T_START=$(date +%s)
SRC=""
T_CHECKPOINT_ESPERA=0

if [[ -f "$DB_NEW" ]]; then
    log "INFO" "Detectado $DB_NAME.new, comprobando si hay checkpoint en progreso..."
    waited=0
    while checkpoint_activo; do
        if (( waited >= MAX_WAIT )); then
            alert \
                "Checkpoint en progreso tras ${MAX_WAIT}s de espera. Usando $DB_NAME como fallback." \
                "El checkpoint de LambdaMOO lleva más de ${MAX_WAIT}s sin completarse.

Fichero de checkpoint esperado : ${DB_NEW}.#<PID>#
Tiempo máximo de espera        : ${MAX_WAIT}s
Acción tomada                  : usar $DB como fuente de backup (fallback)

Comprueba si el proceso moo está bloqueado o si hay un fichero .#*
huérfano en $(dirname "$DB_NEW")."
            break
        fi
        log "INFO" "Checkpoint en progreso, esperando 10s... (${waited}s acumulados)"
        sleep 10
        (( waited += 10 ))
    done
    T_CHECKPOINT_ESPERA=$waited

    if ! checkpoint_activo; then
        SRC="$DB_NEW"
        SRC_TYPE="último checkpoint"
        log "INFO" "Fuente seleccionada: $DB_NAME.new (último checkpoint)"
    fi
fi

if [[ -z "$SRC" ]]; then
    if [[ ! -f "$DB" ]]; then
        log "ERROR" "No se encuentra ninguna fuente de backup: ni $DB ni $DB_NEW"
        exit 1
    fi
    SRC="$DB"
    SRC_TYPE="fallback (sin checkpoint reciente)"
    log "INFO" "Fuente seleccionada: $DB_NAME (fallback)"
fi

# Verificar espacio libre antes de copiar.
# Necesitamos la DB sin comprimir + su .gz temporal (gzip los mantiene ambos
# a la vez durante la compresión), así que reservamos 2× el tamaño de la fuente.
SRC_BYTES=$(stat -c '%s' "$SRC")
FREE_BYTES=$(df --output=avail -B1 "$BACKUP_DIR" | tail -1)
NEEDED=$(( SRC_BYTES * 2 ))
if (( FREE_BYTES < NEEDED )); then
    FREE_H=$(numfmt --to=iec "$FREE_BYTES")
    NEEDED_H=$(numfmt --to=iec "$NEEDED")
    LISTA_BACKUPS=$(find "$BACKUP_DIR" -type f -name "${DB_NAME%.db}_*.db.gz" | sort | \
        while IFS= read -r f; do
            printf "  %s  %s\n" "$(du -h "$f" | cut -f1)" "$(basename "$f")"
        done)
    alert \
        "Espacio insuficiente: disponible ${FREE_H}, necesario ~${NEEDED_H}. Backup cancelado." \
        "Espacio insuficiente en $BACKUP_DIR: disponible ${FREE_H}, necesario ~${NEEDED_H}. Backup cancelado.

Backups actuales en $BACKUP_DIR:
${LISTA_BACKUPS:-  (ninguno)}" \
        "ERROR"
    exit 1
fi

# Copia y compresión — el trap limpia archivos parciales si el proceso se interrumpe
trap 'log "WARN" "Backup interrumpido. Limpiando archivos temporales..."; rm -f "$RAW_DEST" "$DEST"; exit 130' INT TERM

cp "$SRC" "$RAW_DEST"
log "OK" "Backup creado (sin comprimir): $RAW_DEST"

gzip -6 "$RAW_DEST"
T_END=$(date +%s)
DURACION=$(( T_END - T_START ))
DURACION_COPIA=$(( DURACION - T_CHECKPOINT_ESPERA ))
log "OK" "Backup comprimido: $DEST (espera checkpoint: ${T_CHECKPOINT_ESPERA}s, copia+compresión: ${DURACION_COPIA}s, total: ${DURACION}s)"

if ! gzip -t "$DEST" 2>/dev/null; then
    alert "El backup comprimido $DEST está corrupto (gzip -t falló). Revisa el disco."
    rm -f "$DEST"
    exit 1
fi
log "OK" "Integridad verificada: $DEST"
trap - INT TERM

# Rotación: eliminar backups cuya fecha en el nombre supere RETENTION_DAYS.
# Usamos la fecha del nombre (lambdacore_YYYYMMDD_HHMM.db.gz) en vez de -mtime
# para evitar borrados incorrectos si el sistema de archivos toca los archivos.
CUTOFF=$(date -d "-${RETENTION_DAYS} days" '+%Y%m%d')
ELIMINADOS=0
while IFS= read -r file; do
    basename="$(basename "$file")"
    # Extraer YYYYMMDD del nombre (posición fija tras el prefijo "lambdacore_")
    filedate="${basename#lambdacore_}"   # 20260505_0300.db.gz
    filedate="${filedate%%_*}"           # 20260505
    if [[ "$filedate" =~ ^[0-9]{8}$ ]] && [[ ! "$filedate" > "$CUTOFF" ]]; then
        log "INFO" "Eliminando backup antiguo: $file ($filedate < $CUTOFF)"
        rm -f "$file"
        (( ELIMINADOS += 1 ))
    fi
done < <(find "$BACKUP_DIR" -type f -name "${DB_NAME%.db}_*.db.gz" | sort)
if (( ELIMINADOS > 0 )); then
    log "INFO" "Rotación: $ELIMINADOS backup(s) eliminado(s) (antigüedad > ${RETENTION_DAYS} días)"
fi

TOTAL_BACKUPS=$(find "$BACKUP_DIR" -type f -name "${DB_NAME%.db}_*.db.gz" | wc -l)
DEST_SIZE=$(du -h "$DEST" | cut -f1)
DIR_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
FREE_H=$(df -h --output=avail "$BACKUP_DIR" | tail -1 | tr -d ' ')
log "OK" "Backups en rotación: $TOTAL_BACKUPS — carpeta: $DIR_SIZE — disco libre: $FREE_H"
SRC_LABEL="$(basename "$SRC") ($SRC_TYPE)"
echo "Backup completado: $(basename "$DEST") ($DEST_SIZE) — $TOTAL_BACKUPS backups en rotación.
Fuente utilizada             : $SRC_LABEL
Duración del backup          : ${DURACION}s (espera checkpoint: ${T_CHECKPOINT_ESPERA}s, copia+compresión: ${DURACION_COPIA}s)
Tamaño total carpeta backups : $DIR_SIZE
Espacio libre en disco       : $FREE_H" \
    | mail -s "[OK] Backup MOO $(date '+%Y-%m-%d')" "$ALERT_EMAIL" 2>/dev/null || true
log "OK" "Notificación de éxito enviada a $ALERT_EMAIL"
