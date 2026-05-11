#!/usr/bin/env python3
"""Genera gráfica semanal de conexiones del MOO."""

import csv
import os
from collections import defaultdict
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec

from moo_constants import CSV_FILE

OUTPUT = "/root/MOO-1.8.1/conexiones_semanal.png"
DIAS = 7

ahora = datetime.now()
limite = ahora - timedelta(days=DIAS)

registros = []
with open(CSV_FILE, newline="") as f:
    reader = csv.DictReader(f)
    for fila in reader:
        try:
            ts = datetime.strptime(fila["timestamp"], "%Y-%m-%d %H:%M:%S")
            jugadores = int(fila["jugadores"])
            if ts >= limite:
                registros.append((ts, jugadores))
        except (ValueError, KeyError):
            pass

timestamps = [ts for ts, _ in registros]
jugadores  = [j  for _, j  in registros]

# Media por hora del día
por_hora = defaultdict(list)
for ts, j in registros:
    por_hora[ts.hour].append(j)
horas       = list(range(24))
medias_hora = [sum(por_hora[h]) / len(por_hora[h]) if por_hora[h] else 0 for h in horas]

# Media por día
por_dia = defaultdict(list)
for ts, j in registros:
    por_dia[ts.date()].append(j)
dias_sorted = sorted(por_dia.keys())
medias_dia  = [sum(por_dia[d]) / len(por_dia[d]) for d in dias_sorted]
maximos_dia = [max(por_dia[d]) for d in dias_sorted]

# ── Layout ──────────────────────────────────────────
fig = plt.figure(figsize=(14, 10), facecolor="#0f1117")
gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35,
                        left=0.07, right=0.97, top=0.88, bottom=0.08)

AX_COLOR   = "#1a1d27"
GRID_COLOR = "#2a2d3a"
TEXT_COLOR = "#e0e0e0"
ACC1       = "#4fc3f7"   # azul claro
ACC2       = "#81c784"   # verde
ACC3       = "#ffb74d"   # naranja
SPINE_COLOR = "#3a3d4a"

def estilo_ax(ax, title):
    ax.set_facecolor(AX_COLOR)
    ax.set_title(title, color=TEXT_COLOR, fontsize=11, pad=8, fontweight="bold")
    ax.tick_params(colors=TEXT_COLOR, labelsize=8)
    ax.grid(color=GRID_COLOR, linewidth=0.5, linestyle="--", alpha=0.7)
    for spine in ax.spines.values():
        spine.set_edgecolor(SPINE_COLOR)

# ── 1. Serie temporal completa ───────────────────────
ax1 = fig.add_subplot(gs[0, :])
ax1.fill_between(timestamps, jugadores, alpha=0.25, color=ACC1)
ax1.plot(timestamps, jugadores, color=ACC1, linewidth=0.8)
estilo_ax(ax1, "Jugadores conectados — últimos 7 días")
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %Hh"))
ax1.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
plt.setp(ax1.xaxis.get_majorticklabels(), rotation=35, ha="right")
ax1.set_ylabel("Jugadores", color=TEXT_COLOR, fontsize=9)
ax1.yaxis.set_tick_params(colors=TEXT_COLOR)
ax1.set_xlim(timestamps[0], timestamps[-1])
ax1.set_ylim(bottom=0)

# ── 2. Media por hora ────────────────────────────────
ax2 = fig.add_subplot(gs[1, 0])
hora_pico = medias_hora.index(max(medias_hora))
colores_hora = [ACC3 if h == hora_pico else ACC1 for h in horas]
ax2.bar(horas, medias_hora, color=colores_hora, width=0.8)
estilo_ax(ax2, "Media de jugadores por hora (CEST)")
ax2.set_xlabel("Hora", color=TEXT_COLOR, fontsize=9)
ax2.set_ylabel("Media jugadores", color=TEXT_COLOR, fontsize=9)
ax2.set_xticks(horas[::2])
ax2.set_xticklabels([f"{h:02d}h" for h in horas[::2]])
ax2.annotate(f"Pico\n{hora_pico:02d}:00",
             xy=(hora_pico, medias_hora[hora_pico]),
             xytext=(hora_pico + 2, medias_hora[hora_pico] * 0.85),
             color=ACC3, fontsize=8,
             arrowprops=dict(arrowstyle="->", color=ACC3, lw=1.2))

# ── 3. Media y máximo por día ────────────────────────
ax3 = fig.add_subplot(gs[1, 1])
x = range(len(dias_sorted))
labels = [d.strftime("%d/%m") for d in dias_sorted]
ax3.bar(x, maximos_dia, color=ACC1, alpha=0.35, label="Máximo", width=0.6)
ax3.bar(x, medias_dia,  color=ACC2, alpha=0.85, label="Media",  width=0.6)
estilo_ax(ax3, "Actividad diaria — media y máximo")
ax3.set_xticks(list(x))
ax3.set_xticklabels(labels, rotation=30, ha="right")
ax3.set_ylabel("Jugadores", color=TEXT_COLOR, fontsize=9)
ax3.legend(facecolor=AX_COLOR, edgecolor=SPINE_COLOR,
           labelcolor=TEXT_COLOR, fontsize=8)

# ── Título global ────────────────────────────────────
fig.suptitle(
    f"cyberlife.es:7777  ·  Conexiones {limite.strftime('%d/%m')}–{ahora.strftime('%d/%m/%Y')}",
    color=TEXT_COLOR, fontsize=13, fontweight="bold", y=0.95
)

fig.savefig(OUTPUT, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Gráfica guardada en: {OUTPUT}")
