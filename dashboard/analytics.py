import json
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from database.db import get_violation_stats, get_violations


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
        line=dict(color='#E63946', width=3),
        marker=dict(size=8),
        fill='tozeroy', fillcolor='rgba(230,57,70,0.1)'
    ))
    fig_trend.update_layout(
        title='Violation Trends Over Time',
        xaxis_title='Date', yaxis_title='Violations',
        template='plotly_white',
        margin=dict(l=40, r=20, t=50, b=40),
        height=350
    )
    charts['trend'] = json.dumps(fig_trend, cls=plotly.utils.PlotlyJSONEncoder)

    # 2. Violations by Type (donut chart)
    types = list(stats['by_type'].keys()) if stats['by_type'] else ['No Data']
    type_counts = list(stats['by_type'].values()) if stats['by_type'] else [0]
    colors = ['#E63946', '#457B9D', '#F4A261', '#2A9D8F', '#264653']
    fig_type = go.Figure(data=[go.Pie(
        labels=types, values=type_counts, hole=0.5,
        marker_colors=colors[:len(types)],
        textinfo='label+percent',
        textposition='outside'
    )])
    fig_type.update_layout(
        title='Violations by Type',
        template='plotly_white',
        margin=dict(l=20, r=20, t=50, b=20),
        height=350,
        showlegend=False
    )
    charts['by_type'] = json.dumps(fig_type, cls=plotly.utils.PlotlyJSONEncoder)

    # 3. Violations by Zone (horizontal bar chart)
    zones = list(stats['by_zone'].keys()) if stats['by_zone'] else ['No Zones']
    zone_counts = list(stats['by_zone'].values()) if stats['by_zone'] else [0]
    fig_zone = go.Figure(data=[go.Bar(
        y=zones, x=zone_counts, orientation='h',
        marker_color='#457B9D',
        text=zone_counts, textposition='outside'
    )])
    fig_zone.update_layout(
        title='Incidents by Zone',
        xaxis_title='Count', yaxis_title='Zone',
        template='plotly_white',
        margin=dict(l=80, r=20, t=50, b=40),
        height=350
    )
    charts['by_zone'] = json.dumps(fig_zone, cls=plotly.utils.PlotlyJSONEncoder)

    # 4. Peak Violation Hours (bar chart)
    hours = [f'{int(h):02d}:00' for h in stats['by_hour'].keys()] if stats['by_hour'] else ['N/A']
    hour_counts = list(stats['by_hour'].values()) if stats['by_hour'] else [0]
    fig_hours = go.Figure(data=[go.Bar(
        x=hours, y=hour_counts,
        marker_color='#F4A261',
        text=hour_counts, textposition='outside'
    )])
    fig_hours.update_layout(
        title='Peak Violation Hours',
        xaxis_title='Hour of Day', yaxis_title='Violations',
        template='plotly_white',
        margin=dict(l=40, r=20, t=50, b=40),
        height=350
    )
    charts['peak_hours'] = json.dumps(fig_hours, cls=plotly.utils.PlotlyJSONEncoder)

    # 5. Compliance rate
    total = stats['total']
    # We'll estimate total worker-frames from the violations table
    # For the demo, compliance = inverse of violation rate
    charts['total_violations'] = total
    charts['stats'] = stats

    return charts
