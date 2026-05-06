#!/bin/bash
# Script de arranque del servidor LambdaMOO para systemd.
# Gestiona la rotación de la base de datos antes de iniciar.

set -euo pipefail

MOO_DIR="/root/MOO-1.8.1"
DB="$MOO_DIR/lambdacore.db"
DB_NEW="$MOO_DIR/lambdacore.db.new"
PORT=7777

cd "$MOO_DIR"

# Si existe un checkpoint previo (.new), promoverlo a DB activa
if [[ -f "$DB_NEW" ]]; then
    echo "[INFO] Encontrado $DB_NEW, promoviendo a $DB..."
    mv "$DB" "${DB}.old" 2>/dev/null || true
    mv "$DB_NEW" "$DB"
    rm -f "${DB}.old"
    echo "[INFO] Rotación completada."
fi

echo "[INFO] Iniciando LambdaMOO en puerto $PORT..."
exec ./moo "$DB" "$DB_NEW" "$PORT"
