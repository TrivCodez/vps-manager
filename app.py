import os
import random
import string
import subprocess
import sqlite3
import hashlib
import secrets
import time
import json
import psutil
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import docker
import re

def strip_ansi(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', text)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://"
)

DATABASE = 'database.db'
SERVER_LIMIT = 5
client = docker.from_env()

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            api_key TEXT,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            node_id INTEGER DEFAULT NULL,
            container_id TEXT,
            container_name TEXT,
            ssh_command TEXT,
            status TEXT DEFAULT 'creating',
            os_type TEXT DEFAULT 'ubuntu-22.04',
            ram TEXT DEFAULT '2GB',
            cpu TEXT DEFAULT '1 vCPU',
            disk TEXT DEFAULT '20GB',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS port_forwards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            vps_id INTEGER NOT NULL,
            local_port INTEGER NOT NULL,
            remote_port INTEGER NOT NULL,
            serveo_url TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (vps_id) REFERENCES vps(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            resource TEXT,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_name TEXT DEFAULT 'VPS Manager',
            site_description TEXT DEFAULT 'High-Performance VPS Management Panel',
            footer_text TEXT DEFAULT 'Powered by VPS Manager',
            timezone TEXT DEFAULT 'UTC',
            registration_enabled INTEGER DEFAULT 1,
            logo_url TEXT DEFAULT '/static/img/logo.png',
            favicon_url TEXT DEFAULT '/static/img/favicon.ico',
            cpu_threshold INTEGER DEFAULT 90,
            ram_threshold INTEGER DEFAULT 90,
            max_vps_per_user INTEGER DEFAULT 5,
            max_ports_per_user INTEGER DEFAULT 20
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            hostname TEXT NOT NULL,
            node_url TEXT DEFAULT '',
            api_key TEXT DEFAULT '',
            status TEXT DEFAULT 'online',
            vps_count INTEGER DEFAULT 0,
            max_vps INTEGER DEFAULT 500,
            cpu_usage REAL DEFAULT 0,
            ram_usage REAL DEFAULT 0,
            is_local INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT DEFAULT 'info',
            message TEXT NOT NULL,
            source TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vps_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            docker_image TEXT NOT NULL,
            size_mb REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vps_id) REFERENCES vps(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()

    migrations = [
        ("ALTER TABLE settings ADD COLUMN port_forwarding_method TEXT DEFAULT 'serveo'", []),
        ("ALTER TABLE settings ADD COLUMN public_ipv4 TEXT DEFAULT ''", []),
        ("ALTER TABLE port_forwards ADD COLUMN method TEXT DEFAULT 'serveo'", []),
        ("ALTER TABLE port_forwards ADD COLUMN socat_pid INTEGER DEFAULT NULL", []),
        ("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0", []),
        ("ALTER TABLE settings ADD COLUMN icon_path TEXT DEFAULT ''", []),
        ("ALTER TABLE settings ADD COLUMN rate_limit_auth INTEGER DEFAULT 10", []),
        ("ALTER TABLE settings ADD COLUMN rate_limit_api INTEGER DEFAULT 60", []),
        ("ALTER TABLE settings ADD COLUMN rate_limit_heavy INTEGER DEFAULT 5", []),
        ("ALTER TABLE vps ADD COLUMN max_backups INTEGER DEFAULT 0", []),
        ("ALTER TABLE vps ADD COLUMN expires_at TIMESTAMP DEFAULT NULL", []),
        ("ALTER TABLE settings ADD COLUMN default_vps_days INTEGER DEFAULT 0", []),
    ]
    for sql, params in migrations:
        try:
            conn.execute(sql, params)
        except:
            pass
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_api_key():
    return 'fwa-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=32))

def log_activity(user_id, action, resource=None, details=None, ip_address=None):
    conn = get_db()
    conn.execute('INSERT INTO activity_log (user_id, action, resource, details, ip_address) VALUES (?, ?, ?, ?, ?)',
                (user_id, action, resource, details, ip_address))
    conn.commit()
    conn.close()

def add_log(level, message, source='system'):
    conn = get_db()
    conn.execute('INSERT INTO system_logs (level, message, source) VALUES (?, ?, ?)',
                (level, message, source))
    conn.commit()
    conn.close()

def migrate_nodes():
    conn = get_db()
    try:
        conn.execute('ALTER TABLE nodes ADD COLUMN node_url TEXT DEFAULT ""')
    except:
        pass
    try:
        conn.execute('ALTER TABLE nodes ADD COLUMN api_key TEXT DEFAULT ""')
    except:
        pass
    try:
        conn.execute('ALTER TABLE vps ADD COLUMN node_id INTEGER DEFAULT NULL')
    except:
        pass
    try:
        conn.execute('ALTER TABLE settings ADD COLUMN max_ports_per_user INTEGER DEFAULT 20')
    except:
        pass
    try:
        conn.execute('ALTER TABLE settings ADD COLUMN icon_path TEXT DEFAULT ""')
    except:
        pass
    try:
        conn.execute('ALTER TABLE settings ADD COLUMN rate_limit_auth INTEGER DEFAULT 10')
    except:
        pass
    try:
        conn.execute('ALTER TABLE settings ADD COLUMN rate_limit_api INTEGER DEFAULT 60')
    except:
        pass
    try:
        conn.execute('ALTER TABLE settings ADD COLUMN rate_limit_heavy INTEGER DEFAULT 5')
    except:
        pass
    try:
        conn.execute('ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0')
    except:
        pass
    conn.commit()
    conn.close()

def call_node_api(node_url, api_key, endpoint, method='GET', data=None):
    import requests as req
    url = f"{node_url.rstrip('/')}{endpoint}"
    headers = {'X-API-Key': api_key, 'Content-Type': 'application/json'}
    try:
        if method == 'GET':
            r = req.get(url, headers=headers, timeout=30)
        elif method == 'POST':
            r = req.post(url, headers=headers, json=data, timeout=30)
        elif method == 'DELETE':
            r = req.delete(url, headers=headers, timeout=30)
        else:
            return {'error': 'Invalid method'}, 400
        return r.json(), r.status_code
    except req.exceptions.ConnectionError:
        return {'error': 'Node unreachable'}, 502
    except req.exceptions.Timeout:
        return {'error': 'Node timeout'}, 504
    except Exception as e:
        return {'error': str(e)}, 500

def get_node_for_vps(vps_id):
    conn = get_db()
    vps = conn.execute('SELECT * FROM vps WHERE id = ?', (vps_id,)).fetchone()
    if not vps:
        conn.close()
        return None, None
    node = conn.execute('SELECT * FROM nodes WHERE id = ?', (vps['node_id'],)).fetchone() if vps['node_id'] else None
    if not node:
        node = conn.execute('SELECT * FROM nodes WHERE is_local = 1 LIMIT 1').fetchone()
    conn.close()
    return vps, node

def get_settings():
    conn = get_db()
    settings = conn.execute('SELECT * FROM settings LIMIT 1').fetchone()
    if not settings:
        conn.execute('INSERT INTO settings DEFAULT VALUES')
        conn.commit()
        settings = conn.execute('SELECT * FROM settings LIMIT 1').fetchone()
    conn.close()
    return settings

def get_rate_limit(tier='api'):
    settings = get_settings()
    defaults = {'auth': '10/minute', 'api': '60/minute', 'heavy': '5/minute'}
    col = f'rate_limit_{tier}'
    if col in settings.keys():
        val = settings[col]
        if val and int(val) > 0:
            return f"{val}/minute"
    return defaults.get(tier, '60/minute')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'error')
            return redirect(url_for('login'))
        conn = get_db()
        user = conn.execute('SELECT is_banned FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        if user and user['is_banned']:
            session.clear()
            flash('Your account has been banned', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'error')
            return redirect(url_for('login'))
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        if not user or not user['is_admin']:
            flash('Admin access required', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def get_container_ip(container_id):
    try:
        import subprocess
        result = subprocess.run(
            ['docker', 'inspect', '-f', '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}', container_id],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except:
        return None

def start_socat_local(listen_ip, port, container_ip, container_port=None):
    import subprocess, os, signal, time
    if not container_port:
        container_port = port
    pidfile = f'/tmp/socat_{port}.pid'
    logfile = f'/tmp/socat_{port}.log'

    if os.path.exists(pidfile):
        try:
            with open(pidfile) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, signal.SIGTERM)
            time.sleep(0.5)
        except:
            pass

    proc = subprocess.Popen(
        ['socat', f'TCP-LISTEN:{port},bind=0.0.0.0,reuseaddr,fork', f'TCP:{container_ip}:{container_port}'],
        stdout=open(logfile, 'w'),
        stderr=subprocess.STDOUT,
        start_new_session=True
    )

    with open(pidfile, 'w') as f:
        f.write(str(proc.pid))

    return proc.pid

def stop_socat_local(port, pid=None):
    import os, signal
    if pid:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except:
            pass
    pidfile = f'/tmp/socat_{port}.pid'
    if os.path.exists(pidfile):
        try:
            with open(pidfile) as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, signal.SIGTERM)
        except:
            pass
        try:
            os.remove(pidfile)
        except:
            pass

def get_random_free_port():
    import socket
    for _ in range(20):
        port = random.randint(30000, 60000)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                continue
    raise Exception('No free ports available')

def generate_container_name():
    return 'vps-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))