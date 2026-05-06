#!/bin/bash
set -euo pipefail

BACKUP_DIR="/root/MOO-1.8.1/backups"
DEST="/root/MOO-1.8.1/lambdacore.db"

# Comprobar que el servidor MOO no está en ejecución
if systemctl is-active --quiet lambdamoo.service; then
    echo "[ERROR] El servidor LambdaMOO está activo (lambdamoo.service)."
    echo "        Detén el servidor antes de restaurar:"
    echo "          systemctl stop lambdamoo.service"
    exit 1
fi

if pgrep -x moo > /dev/null 2>&1; then
    echo "[ERROR] Se detecta un proceso 'moo' en ejecución fuera de systemd."
    echo "        Detén el servidor antes de restaurar."
    exit 1
fi

cd "$BACKUP_DIR"

# Buscar el backup más reciente por fecha en el nombre (YYYYMMDD_HHMM),
# no por fecha de modificación del sistema de archivos.
LATEST=""
LATEST_KEY=""
for f in lambdacore_*.db.gz lambdacore_*.db; do
    [[ -f "$f" ]] || continue
    # Extraer YYYYMMDD_HHMM del nombre: lambdacore_20260505_0300.db[.gz]
    key="${f#lambdacore_}"   # 20260505_0300.db[.gz]
    key="${key%%.db*}"       # 20260505_0300
    if [[ "$key" > "$LATEST_KEY" ]]; then
        LATEST_KEY="$key"
        LATEST="$f"
    fi
done

if [[ -z "$LATEST" ]]; then
    echo "[ERROR] No se encontró ningún backup en $BACKUP_DIR"
    exit 1
fi

BACKUP_SIZE=$(du -h "$BACKUP_DIR/$LATEST" | cut -f1)

# Formatear fecha legible a partir del nombre (lambdacore_YYYYMMDD_HHMM.db[.gz])
_base="${LATEST#lambdacore_}"           # 20260505_0300.db[.gz]
_datepart="${_base%%_*}"               # 20260505
_timepart="${_base#*_}"; _timepart="${_timepart%%.*}"  # 0300
FECHA_LEGIBLE=$(date -d "${_datepart:0:4}-${_datepart:4:2}-${_datepart:6:2} ${_timepart:0:2}:${_timepart:2:2}" \
    '+%-d %b %Y a las %H:%M' 2>/dev/null || echo "$_datepart ${_timepart:0:2}:${_timepart:2:2}")

echo "[INFO] Backup más reciente: $LATEST ($BACKUP_SIZE)"
echo "[INFO] Fecha del backup   : $FECHA_LEGIBLE"

# Verificar integridad antes de ofrecer la restauración
if [[ "$LATEST" == *.gz ]]; then
    echo "[INFO] Verificando integridad del backup..."
    if ! gzip -t "$BACKUP_DIR/$LATEST" 2>/dev/null; then
        echo "[ERROR] El backup $LATEST está corrupto (gzip -t falló). Restauración cancelada."
        exit 1
    fi
    echo "[OK] Integridad verificada."
fi

echo ""
read -r -p "¿Restaurar backup del $FECHA_LEGIBLE ($BACKUP_SIZE) sobre $DEST? [s/N] " CONFIRM
if [[ "${CONFIRM,,}" != "s" ]]; then
    echo "[INFO] Operación cancelada."
    exit 0
fi

# Guardar copia de seguridad de la BD actual antes de sobreescribir.
# Se conserva solo la más reciente; las anteriores se eliminan para no acumular
# copias de ~241 MB cada una.
if [[ -f "$DEST" ]]; then
    # Eliminar copias de seguridad anteriores
    while IFS= read -r old; do
        echo "[INFO] Eliminando copia de seguridad anterior: $old"
        rm -f "$old"
    done < <(find "$(dirname "$DEST")" -maxdepth 1 -name "$(basename "$DEST").antes_restore_*" | sort)

    SAFETY="${DEST}.antes_restore_$(date '+%Y%m%d_%H%M%S')"
    echo "[INFO] Guardando copia de seguridad de la BD actual en: $SAFETY"
    cp "$DEST" "$SAFETY"
fi

# Restaurar en fichero temporal; mv atómico al destino final.
# El trap limpia el temporal si el proceso se interrumpe antes del mv.
DEST_TMP="${DEST}.restore_tmp"
trap 'echo "[WARN] Restauración interrumpida. Limpiando temporal..."; rm -f "$DEST_TMP"; exit 130' INT TERM

if [[ "$LATEST" == *.gz ]]; then
    echo "[INFO] Descomprimiendo..."
    gunzip -c "$BACKUP_DIR/$LATEST" > "$DEST_TMP"
else
    cp "$BACKUP_DIR/$LATEST" "$DEST_TMP"
fi
mv "$DEST_TMP" "$DEST"
trap - INT TERM

echo "[OK] Restaurado desde $LATEST -> $DEST"

# Eliminar checkpoint pendiente para evitar que start_moo.sh lo promueva
# sobre la BD recién restaurada al próximo arranque
DB_NEW="/root/MOO-1.8.1/lambdacore.db.new"
if [[ -f "$DB_NEW" ]]; then
    rm -f "$DB_NEW"
    echo "[INFO] Eliminado lambdacore.db.new (evita promoción involuntaria al arrancar)."
fi

echo ""
echo "Para arrancar el servidor:"
echo "  systemctl start lambdamoo.service"
