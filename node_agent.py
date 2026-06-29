#!/usr/bin/env python3
"""
VPS Manager - Node Agent
Runs on each remote VPS node. Handles all Docker operations.
Panel communicates with this agent via HTTP API.

Usage:
  pip3 install flask docker psutil
  sudo bash setup_node.sh
  python3 node_agent.py

Or just run this file — it auto-installs dependencies.
"""

import os, sys, json, secrets, re, subprocess
from functools import wraps

# Auto-install dependencies if missing
def ensure_deps():
    missing = []
    for mod, pkg in [('flask', 'flask'), ('docker', 'docker'), ('psutil', 'psutil')]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[setup] Installing missing packages: {', '.join(missing)}")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q'] + missing)

ensure_deps()

from flask import Flask, request, jsonify
import docker

def strip_ansi(text):
    return re.sub(r'\x1b\[[0-9;]*m', '', text)

app = Flask(__name__)
client = docker.from_env()

API_KEY = os.environ.get('NODE_API_KEY', secrets.token_hex(32))
LISTEN_PORT = int(os.environ.get('NODE_PORT', 5001))


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if key != API_KEY:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/api/info')
@require_api_key
def node_info():
    import psutil
    return jsonify({
        'status': 'ok',
        'cpu_percent': psutil.cpu_percent(interval=0.5),
        'ram_percent': psutil.virtual_memory().percent,
        'ram_total_gb': round(psutil.virtual_memory().total / (1024**3), 1),
        'disk_total_gb': round(psutil.disk_usage('/').total / (1024**3), 1),
        'disk_used_gb': round(psutil.disk_usage('/').used / (1024**3), 1),
    })


@app.route('/api/containers')
@require_api_key
def list_containers():
    containers = client.containers.list(all=True)
    result = []
    for c in containers:
        result.append({
            'id': c.id[:12],
            'name': c.name,
            'status': c.status,
        })
    return jsonify({'containers': result})


@app.route('/api/container/create', methods=['POST'])
@require_api_key
def create_container():
    data = request.get_json()
    name = data.get('name')
    image = data.get('image', 'vps-ubuntu:latest')
    ram = data.get('ram')
    cpu = data.get('cpu')
    disk = data.get('disk')

    if not name:
        return jsonify({'error': 'Name is required'}), 400

    try:
        kwargs = {
            'detach': True,
            'name': name,
            'hostname': name,
        }

        if cpu:
            try:
                cpu_val = int(''.join(filter(str.isdigit, cpu)))
                kwargs['nano_cpus'] = cpu_val * 10**9
            except:
                pass

        if ram:
            ram_lower = ram.lower()
            try:
                if 'gb' in ram_lower:
                    mem_bytes = int(ram_lower.replace('gb', '').strip()) * 1024**3
                elif 'mb' in ram_lower:
                    mem_bytes = int(ram_lower.replace('mb', '').strip()) * 1024**2
                else:
                    mem_bytes = int(ram_lower) * 1024**3
                kwargs['mem_limit'] = mem_bytes
            except:
                pass

        container = client.containers.run(image, **kwargs)

        return jsonify({
            'status': 'ok',
            'container_id': container.id,
            'name': name,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/start', methods=['POST'])
@require_api_key
def start_container(container_id):
    try:
        container = client.containers.get(container_id)
        container.start()
        return jsonify({'status': 'ok', 'state': container.status})
    except docker.errors.NotFound:
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/stop', methods=['POST'])
@require_api_key
def stop_container(container_id):
    try:
        container = client.containers.get(container_id)
        container.stop()
        return jsonify({'status': 'ok', 'state': container.status})
    except docker.errors.NotFound:
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/restart', methods=['POST'])
@require_api_key
def restart_container(container_id):
    try:
        container = client.containers.get(container_id)
        container.restart()
        return jsonify({'status': 'ok', 'state': container.status})
    except docker.errors.NotFound:
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/delete', methods=['POST'])
@require_api_key
def delete_container(container_id):
    try:
        container = client.containers.get(container_id)
        container.stop(timeout=5)
        container.remove()
        return jsonify({'status': 'ok'})
    except docker.errors.NotFound:
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/status')
@require_api_key
def container_status(container_id):
    try:
        container = client.containers.get(container_id)
        return jsonify({
            'status': 'ok',
            'state': container.status,
            'id': container.id,
        })
    except docker.errors.NotFound:
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/stats')
@require_api_key
def container_stats(container_id):
    try:
        container = client.containers.get(container_id)
        stats = container.stats(stream=False)

        cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
        system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
        num_cpus = stats['cpu_stats']['online_cpus']
        cpu_percent = (cpu_delta / system_delta * num_cpus * 100.0) if system_delta > 0 else 0

        mem_usage = stats['memory_stats'].get('usage', 0)
        mem_limit = stats['memory_stats'].get('limit', 1)
        mem_percent = (mem_usage / mem_limit * 100.0)

        networks = stats.get('networks', {})
        net_rx = sum(v.get('rx_bytes', 0) for v in networks.values())
        net_tx = sum(v.get('tx_bytes', 0) for v in networks.values())

        pids = stats.get('pids_stats', {}).get('current', 0)

        return jsonify({
            'cpu_percent': round(cpu_percent, 1),
            'memory_used': round(mem_usage / 1024**2),
            'memory_total': round(mem_limit / 1024**2),
            'memory_percent': round(mem_percent, 1),
            'net_rx': net_rx,
            'net_tx': net_tx,
            'pids': pids,
        })
    except docker.errors.NotFound:
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/regen-ssh', methods=['POST'])
@require_api_key
def regen_ssh(container_id):
    try:
        container = client.containers.get(container_id)
        if container.status != 'running':
            container.start()
            import time
            time.sleep(2)

        try:
            container.exec_run('pkill sshx', stdout=True, stderr=True)
            import time
            time.sleep(1)
        except:
            pass

        ssh_session_line = None
        exec_result = container.exec_run('sshx', stream=True)
        for line in exec_result.output:
            decoded = strip_ansi(line.decode('utf-8', errors='ignore').strip())
            if 'Link:' in decoded and 'sshx.io' in decoded:
                ssh_session_line = decoded.split('Link:')[1].strip().split()[0]
                break

        if ssh_session_line:
            return jsonify({'status': 'ok', 'ssh_command': ssh_session_line, 'method': 'sshx'})
        else:
            return jsonify({'error': 'Failed to get sshx session'}), 500
    except docker.errors.NotFound:
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/exec', methods=['POST'])
@require_api_key
def exec_in_container(container_id):
    data = request.get_json()
    command = data.get('command')
    detach = data.get('detach', False)

    if not command:
        return jsonify({'error': 'Command is required'}), 400

    try:
        container = client.containers.get(container_id)
        result = container.exec_run(command, stdout=True, stderr=True, stream=False, detach=detach)
        return jsonify({
            'status': 'ok',
            'output': result.output.decode('utf-8') if result.output else '',
            'exit_code': result.exit_code,
        })
    except docker.errors.NotFound:
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/socat/start', methods=['POST'])
@require_api_key
def socat_start():
    data = request.get_json()
    listen_ip = data.get('listen_ip')
    port = data.get('port')
    container_ip = data.get('container_ip')
    container_port = data.get('container_port', port)

    if not all([listen_ip, port, container_ip]):
        return jsonify({'error': 'listen_ip, port, and container_ip are required'}), 400

    try:
        import subprocess, signal, os, time
        pidfile = f'/tmp/socat_{port}.pid'
        logfile = f'/tmp/socat_{port}.log'

        if os.path.exists(pidfile):
            with open(pidfile) as f:
                old_pid = int(f.read().strip())
            try:
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

        return jsonify({'status': 'ok', 'pid': proc.pid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/socat/stop', methods=['POST'])
@require_api_key
def socat_stop():
    data = request.get_json()
    port = data.get('port')
    pid = data.get('pid')

    if not port:
        return jsonify({'error': 'port is required'}), 400

    try:
        import os, signal
        if pid:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except:
                pass

        pidfile = f'/tmp/socat_{port}.pid'
        if os.path.exists(pidfile):
            with open(pidfile) as f:
                old_pid = int(f.read().strip())
            try:
                os.kill(old_pid, signal.SIGTERM)
            except:
                pass
            os.remove(pidfile)

        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/container/<container_id>/ip', methods=['GET'])
@require_api_key
def get_container_ip(container_id):
    try:
        container = client.containers.get(container_id)
        ip = None
        for net in container.attrs['NetworkSettings']['Networks'].values():
            if net.get('IPAddress'):
                ip = net['IPAddress']
                break
        return jsonify({'ip': ip or ''})
    except docker.errors.NotFound:
        return jsonify({'error': 'Container not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print(f"[node-agent] Starting on port {LISTEN_PORT}")
    print(f"[node-agent] API Key: {API_KEY}")
    app.run(host='0.0.0.0', port=LISTEN_PORT, debug=False)