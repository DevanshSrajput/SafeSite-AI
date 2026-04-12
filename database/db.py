import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database', 'safesiteai.db')


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            violation_type TEXT NOT NULL,
            zone_name TEXT DEFAULT '',
            screenshot_path TEXT DEFAULT '',
            confidence_score REAL DEFAULT 0.0
        )
    ''')
    conn.commit()
    conn.close()


def log_violation(violation_type, zone_name='', screenshot_path='', confidence_score=0.0):
    conn = get_connection()
    cursor = conn.cursor()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT INTO violations (timestamp, violation_type, zone_name, screenshot_path, confidence_score)
        VALUES (?, ?, ?, ?, ?)
    ''', (timestamp, violation_type, zone_name, screenshot_path, confidence_score))
    conn.commit()
    violation_id = cursor.lastrowid
    conn.close()
    return violation_id


def get_violations(start_date=None, end_date=None, violation_type=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = 'SELECT * FROM violations WHERE 1=1'
    params = []

    if start_date:
        query += ' AND timestamp >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND timestamp <= ?'
        params.append(end_date + ' 23:59:59')
    if violation_type:
        query += ' AND violation_type = ?'
        params.append(violation_type)

    query += ' ORDER BY timestamp DESC'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_violation_stats():
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    cursor.execute('SELECT COUNT(*) as total FROM violations')
    stats['total'] = cursor.fetchone()['total']

    cursor.execute('SELECT violation_type, COUNT(*) as count FROM violations GROUP BY violation_type')
    stats['by_type'] = {row['violation_type']: row['count'] for row in cursor.fetchall()}

    cursor.execute('SELECT zone_name, COUNT(*) as count FROM violations WHERE zone_name != "" GROUP BY zone_name')
    stats['by_zone'] = {row['zone_name']: row['count'] for row in cursor.fetchall()}

    cursor.execute('''
        SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
        FROM violations GROUP BY hour ORDER BY hour
    ''')
    stats['by_hour'] = {row['hour']: row['count'] for row in cursor.fetchall()}

    cursor.execute('''
        SELECT DATE(timestamp) as date, COUNT(*) as count
        FROM violations GROUP BY date ORDER BY date
    ''')
    stats['by_date'] = {row['date']: row['count'] for row in cursor.fetchall()}

    conn.close()
    return stats


init_db()
