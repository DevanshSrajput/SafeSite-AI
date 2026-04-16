import json
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from database.db import get_violation_stats, get_violations


INK = '#0a0a0a'
YELLOW = '#ffd60a'
CYAN = '#4fc3f7'
PINK = '#ff2e93'
RED = '#ff3b30'
GREEN = '#00e676'
ORANGE = '#ff8c00'
PAPER = '#f5f2e8'


def _brutal_layout(title, xtitle='', ytitle=''):
    return dict(
        title=dict(text=f'<b>{title.upper()}</b>', font=dict(family='Archivo Black, Impact, sans-serif', size=16, color=INK)),
        xaxis=dict(title=xtitle, gridcolor=INK, gridwidth=1, linecolor=INK, linewidth=2, tickfont=dict(color=INK, family='Space Grotesk, sans-serif')),
        yaxis=dict(title=ytitle, gridcolor=INK, gridwidth=1, linecolor=INK, linewidth=2, tickfont=dict(color=INK, family='Space Grotesk, sans-serif')),
        plot_bgcolor=PAPER,
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(family='Space Grotesk, sans-serif', color=INK),
        margin=dict(l=60, r=30, t=60, b=50),
        height=340,
    )


def generate_dashboard_data():
    """Generate all Plotly charts for the analytics dashboard. Returns JSON strings."""
    stats = get_violation_stats()
    charts = {}

    # 1. Violation Trends Over Time (line chart)
    dates = list(stats['by_date'].keys())
    counts = list(stats['by_date'].values())
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=dates, y=counts, mode='lines+markers',
        line=dict(color=RED, width=4),
        marker=dict(size=12, color=YELLOW, line=dict(color=INK, width=2)),
        fill='tozeroy', fillcolor='rgba(255,59,48,0.18)'
    ))
    fig_trend.update_layout(**_brutal_layout('Violation Trends', 'Date', 'Violations'))
    charts['trend'] = json.dumps(fig_trend, cls=plotly.utils.PlotlyJSONEncoder)

    # 2. Violations by Type (donut chart)
    types = list(stats['by_type'].keys()) if stats['by_type'] else ['No Data']
    type_counts = list(stats['by_type'].values()) if stats['by_type'] else [0]
    donut_colors = [RED, CYAN, PINK, GREEN, ORANGE]
    fig_type = go.Figure(data=[go.Pie(
        labels=types, values=type_counts, hole=0.55,
        marker=dict(colors=donut_colors[:len(types)], line=dict(color=INK, width=3)),
        textinfo='label+percent',
        textposition='outside',
        textfont=dict(family='Archivo Black, Impact, sans-serif', size=13, color=INK)
    )])
    layout = _brutal_layout('Violations by Type')
    layout['showlegend'] = False
    fig_type.update_layout(**layout)
    charts['by_type'] = json.dumps(fig_type, cls=plotly.utils.PlotlyJSONEncoder)

    # 3. Violations by Zone (horizontal bar chart)
    zones = list(stats['by_zone'].keys()) if stats['by_zone'] else ['No Zones']
    zone_counts = list(stats['by_zone'].values()) if stats['by_zone'] else [0]
    fig_zone = go.Figure(data=[go.Bar(
        y=zones, x=zone_counts, orientation='h',
        marker=dict(color=CYAN, line=dict(color=INK, width=3)),
        text=zone_counts, textposition='outside',
        textfont=dict(family='Archivo Black, Impact, sans-serif', color=INK)
    )])
    fig_zone.update_layout(**_brutal_layout('Incidents by Zone', 'Count', 'Zone'))
    charts['by_zone'] = json.dumps(fig_zone, cls=plotly.utils.PlotlyJSONEncoder)

    # 4. Peak Violation Hours (bar chart)
    hours = [f'{int(h):02d}:00' for h in stats['by_hour'].keys()] if stats['by_hour'] else ['N/A']
    hour_counts = list(stats['by_hour'].values()) if stats['by_hour'] else [0]
    fig_hours = go.Figure(data=[go.Bar(
        x=hours, y=hour_counts,
        marker=dict(color=YELLOW, line=dict(color=INK, width=3)),
        text=hour_counts, textposition='outside',
        textfont=dict(family='Archivo Black, Impact, sans-serif', color=INK)
    )])
    fig_hours.update_layout(**_brutal_layout('Peak Violation Hours', 'Hour of Day', 'Violations'))
    charts['peak_hours'] = json.dumps(fig_hours, cls=plotly.utils.PlotlyJSONEncoder)

    # 5. Compliance rate
    total = stats['total']
    # We'll estimate total worker-frames from the violations table
    # For the demo, compliance = inverse of violation rate
    charts['total_violations'] = total
    charts['stats'] = stats

    return charts
