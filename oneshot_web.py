#!/usr/bin/env python3
"""
OneShot WebUI - Cross-platform browser interface for OneShot WPS attack
Same interface everywhere: Linux, Kali, Termux (Android)
All 16 CLI options mapped to GUI controls
"""

import os, sys, re, json, time, io, queue, signal, socket, threading, subprocess, argparse

try:
    from flask import Flask, request, jsonify, Response, render_template_string
except ImportError:
    print("[-] Flask required. Install: pip install flask")
    sys.exit(1)

# Import oneshot classes (not OneShot — that class doesn't exist)
import oneshot
oneshot.args = argparse.Namespace(loop=False, reverse_scan=False)

from oneshot import Companion, WiFiScanner, NetworkAddress, WPSpin

# ============================================================
# Global State
# ============================================================
log_queue = queue.Queue()
stop_event = threading.Event()
scan_results = []
current_vuln_list = []
attack_running = False
current_companion = None
operation_thread = None
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wifi_history.json')

def save_history(essid, bssid, pin, psk, mode):
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except:
            history = []
    entry = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'essid': essid or '',
        'bssid': bssid or '',
        'pin': pin or '',
        'psk': psk or '',
        'mode': mode or '',
    }
    # Don't save if empty
    if not entry['psk'] and not entry['pin']:
        return
    history.append(entry)
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        print(f"[+] Credentials saved to history: {essid}")
    except Exception as e:
        print(f"[-] Failed to save history: {e}")

app = Flask(__name__)

# ============================================================
# Log Capture
# ============================================================
class QueueIO(io.StringIO):
    def __init__(self, q, *a, **kw):
        super().__init__(*a, **kw)
        self._q = q
    def write(self, s):
        if s.strip():
            self._q.put(s)
        return super().write(s)
    def flush(self):
        pass

class LogCapture:
    def __enter__(self):
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        sys.stdout = QueueIO(log_queue)
        sys.stderr = QueueIO(log_queue)
        return self
    def __exit__(self, *a):
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr

# ============================================================
# Helpers
# ============================================================
def get_wifi_interfaces():
    ifaces = []
    seen = set()
    skip_words = {'no', 'ieee', 'essid', 'mode', 'access', 'bit', 'link', 'tx', 'rx',
                  'extra', 'power', 'retry', 'rts', 'frag', 'encryption', 'ap', 'cell'}

    def add_iface(name):
        n = name.strip().rstrip(':')
        if n and n not in seen:
            ifaces.append(n)
            seen.add(n)

    # Method 1: /sys/class/net/ (most reliable — works on Linux & Android)
    try:
        for entry in os.listdir('/sys/class/net/'):
            add_iface(entry)
    except:
        pass

    # Method 2: /proc/net/dev
    try:
        with open('/proc/net/dev') as f:
            for line in f.readlines()[2:]:
                add_iface(line.split(':')[0])
    except:
        pass

    # Method 3: ip link show
    try:
        r = subprocess.run(['ip', 'link', 'show'], capture_output=True, text=True)
        for line in r.stdout.split('\n'):
            if ': <' in line or ': ' in line:
                parts = line.strip().split(': ')
                if len(parts) >= 2:
                    add_iface(parts[1].split('@')[0])  # handle veth@ifXXX
    except:
        pass

    # Method 4: iw dev
    try:
        r = subprocess.run(['iw', 'dev'], capture_output=True, text=True)
        for line in r.stdout.split('\n'):
            if 'Interface' in line:
                add_iface(line.split()[-1])
    except:
        pass

    # Method 5: iwconfig
    try:
        r = subprocess.run(['iwconfig'], capture_output=True, text=True)
        for line in r.stdout.split('\n'):
            sline = line.strip()
            if sline and ' ' in line and not line.startswith((' ', '\t')):
                candidate = line.split()[0].strip()
                if candidate.lower() not in skip_words and not candidate.startswith('('):
                    add_iface(candidate)
    except:
        pass

    # Method 6: ip addr
    try:
        r = subprocess.run(['ip', 'addr'], capture_output=True, text=True)
        for line in r.stdout.split('\n'):
            if ': <' in line or ': ' in line:
                parts = line.strip().split(': ')
                if len(parts) >= 2 and parts[1]:
                    add_iface(parts[1].split('@')[0])
    except:
        pass

    # Deduplicate, filter obvious virtual interfaces, keep wlan/wlp/etc
    wireless_keywords = ('wlan', 'wlp', 'p2p', 'eth', 'ra', 'wfx', 'wl')
    wifi = [i for i in ifaces if i.startswith(wireless_keywords)]
    others = [i for i in ifaces if not i.startswith(wireless_keywords)]
    # Put likely wireless interfaces first
    result = wifi + others

    return result if result else ['wlan0']

def get_own_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def ifaceUp(iface, down=False):
    action = 'down' if down else 'up'
    cmd = 'ip link set {} {}'.format(iface, action)
    res = subprocess.run(cmd, shell=True, stdout=sys.stdout, stderr=sys.stdout)
    return res.returncode == 0

# ============================================================
# Background Workers
# ============================================================
def do_scan_in_thread(iface, vuln_path='', reverse=False):
    global scan_results, current_vuln_list
    oneshot.args.reverse_scan = reverse
    try:
        with LogCapture():
            if not ifaceUp(iface):
                print(f"[-] Failed to bring up {iface}")
                return
            path = vuln_path or os.path.join(os.path.dirname(os.path.realpath(__file__)), 'vulnwsc.txt')
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    current_vuln_list = f.read().splitlines()
            except:
                current_vuln_list = []
            scanner = WiFiScanner(iface, current_vuln_list)
            result = scanner.iw_scanner()
            scan_results = list(result.values()) if result else []
    except Exception as e:
        print(f"[-] Scan error: {e}")
    finally:
        log_queue.put('__SCAN_DONE__')

def do_attack_in_thread(params):
    global attack_running, current_companion
    attack_running = True
    stop_event.clear()

    iface = params.get('iface', 'wlan0')
    bssid = params.get('bssid', '')
    pin = params.get('pin', '')
    delay = params.get('delay', 0)
    pixie = params.get('pixie', False)
    bruteforce = params.get('bruteforce', False)
    pbc = params.get('pbc', False)
    show_cmd = params.get('show_cmd', False)
    pixie_force = params.get('force', False)
    verbose = params.get('verbose', False)
    write = params.get('write', False)
    iface_down = params.get('iface_down', False)
    loop = params.get('loop', False)
    mtk = params.get('mtk', False)
    wmt = None

    try:
        with LogCapture():
            if mtk:
                from pathlib import Path
                wmt = Path('/dev/wmtWifi')
                if wmt.is_char_device():
                    wmt.chmod(0o644)
                    wmt.write_text('1')
                else:
                    print("[-] /dev/wmtWifi not found")
                    return

            if not ifaceUp(iface):
                print(f"[-] Failed to bring up {iface}")
                return

            while True:
                companion = None
                try:
                    if stop_event.is_set():
                        print("[!] Attack stopped by user")
                        break

                    oneshot.args.loop = loop
                    companion = Companion(iface, write, print_debug=verbose)
                    current_companion = companion

                    atk_pin = pin
                    if pbc:
                        atk_pin = '<PBC>'
                        companion.single_connection(pbc_mode=True)
                    elif bruteforce:
                        atk_pin = atk_pin if atk_pin else '0000'
                        companion.smart_bruteforce(bssid, atk_pin, delay)
                    else:
                        if pixie and not atk_pin:
                            atk_pin = WPSpin().getLikely(bssid) or '12345670'
                        companion.single_connection(bssid, atk_pin, pixie, False,
                                                    show_cmd, pixie_force)

                    if companion.connection_status.status == 'GOT_PSK':
                        cs = companion.connection_status
                        save_history(
                            essid=cs.essid or bssid,
                            bssid=cs.bssid or bssid,
                            pin=atk_pin,
                            psk=cs.wpa_psk,
                            mode='pixie' if pixie else 'bruteforce' if bruteforce else 'pbc'
                        )

                    if not loop:
                        break
                except KeyboardInterrupt:
                    if loop:
                        print("[?] Continuing loop...")
                    else:
                        print("\n[!] Aborting…")
                        break
                finally:
                    if companion is not None:
                        try:
                            companion.cleanup()
                        except:
                            pass
                    current_companion = None
    except Exception as e:
        print(f"[-] Attack error: {e}")
    finally:
        if iface_down:
            ifaceUp(iface, down=True)
        if mtk and wmt is not None:
            try:
                wmt.write_text('0')
            except:
                pass
        attack_running = False
        log_queue.put('__ATTACK_DONE__')

# ============================================================
# Flask Routes
# ============================================================
@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/interfaces')
def api_interfaces():
    return jsonify(get_wifi_interfaces())

@app.route('/api/scan')
def api_scan():
    global operation_thread
    iface = request.args.get('interface', 'wlan0')
    vuln_path = request.args.get('vuln_list', '')
    reverse = request.args.get('reverse', 'false').lower() == 'true'
    operation_thread = threading.Thread(target=do_scan_in_thread, args=(iface, vuln_path, reverse), daemon=True)
    operation_thread.start()
    return jsonify({'status': 'ok'})

@app.route('/api/networks')
def api_networks():
    data = []
    for n in scan_results:
        model = '{} {}'.format(n.get('Model', ''), n.get('Model number', '')).strip()
        vuln = bool(current_vuln_list and model in current_vuln_list)
        data.append({
            'bssid': n.get('BSSID', ''),
            'essid': n.get('ESSID', '<hidden>'),
            'channel': n.get('Channel', ''),
            'signal': str(n.get('Level', '')),
            'encrypted': n.get('Security type', ''),
            'wps': str(n.get('WPS', '')),
            'locked': n.get('WPS locked', False),
            'vuln': vuln,
        })
    return jsonify(data)

@app.route('/api/generate_pin')
def api_generate_pin():
    bssid = request.args.get('bssid', '')
    bssid = bssid.replace('-', ':').upper()
    try:
        pin = WPSpin().getLikely(bssid)
        return jsonify({'pin': pin if pin else 'No PIN generated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/attack', methods=['POST'])
def api_attack():
    global operation_thread, attack_running
    if attack_running:
        return jsonify({'error': 'Attack already running'}), 400
    params = request.get_json()
    operation_thread = threading.Thread(target=do_attack_in_thread, args=(params,), daemon=True)
    operation_thread.start()
    return jsonify({'status': 'ok'})

@app.route('/api/stop')
def api_stop():
    global current_companion, attack_running
    stop_event.set()
    attack_running = False
    return jsonify({'status': 'ok'})

@app.route('/api/status')
def api_status():
    return jsonify({
        'running': attack_running,
        'has_results': len(scan_results) > 0,
    })

@app.route('/api/history')
def api_history():
    if not os.path.exists(HISTORY_FILE):
        return jsonify([])
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except:
        return jsonify([])

@app.route('/api/history/clear', methods=['POST'])
def api_history_clear():
    try:
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/stream')
def stream():
    def generate():
        while True:
            try:
                msg = log_queue.get(timeout=30)
                if msg in ('__SCAN_DONE__', '__ATTACK_DONE__'):
                    yield f"event: done\ndata: {json.dumps({'msg': msg})}\n\n"
                else:
                    yield f"data: {json.dumps({'msg': msg})}\n\n"
            except queue.Empty:
                yield ": heartbeat\n\n"
    return Response(generate(), mimetype='text/event-stream')

# ============================================================
# HTML Template
# ============================================================
HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OPX OneShot v0.0.2</title>
<style>
:root {
  --bg: #0d1117;
  --surface: #161b22;
  --border: #30363d;
  --text: #c9d1d9;
  --text-dim: #8b949e;
  --accent: #58a6ff;
  --green: #3fb950;
  --red: #f85149;
  --orange: #d29922;
  --radius: 6px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  padding: 16px; min-height: 100vh;
}
.container { max-width: 960px; margin: 0 auto; }
.header {
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;
  padding: 12px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 12px;
}
.header h1 { font-size: 18px; display: flex; align-items: center; gap: 8px; }
.header h1 span { color: var(--accent); }
.iface-group { display: flex; align-items: center; gap: 8px; }
.iface-group label { font-size: 13px; color: var(--text-dim); }
.iface-group select {
  background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 4px;
  padding: 4px 8px; font-size: 13px; cursor: pointer;
}
.row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.col { flex: 1; min-width: 280px; }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; margin-bottom: 12px;
}
.card-title { font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 8px; }
.btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; border: 1px solid var(--border);
  border-radius: 4px; font-size: 13px; cursor: pointer; background: var(--bg); color: var(--text); transition: .15s;
  white-space: nowrap;
}
.btn:hover { border-color: var(--text-dim); }
.btn-primary { background: #1f6feb; border-color: #1f6feb; color: #fff; }
.btn-primary:hover { background: #388bfd; }
.btn-danger { background: #da3633; border-color: #da3633; color: #fff; }
.btn-danger:hover { background: #f85149; }
.btn-success { background: #238636; border-color: #238636; color: #fff; }
.btn-success:hover { background: #2ea043; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
input, select {
  background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: 4px;
  padding: 5px 8px; font-size: 13px; font-family: inherit; width: 100%;
}
input:focus, select:focus { outline: none; border-color: var(--accent); }
label { font-size: 13px; color: var(--text-dim); }
.field { margin-bottom: 8px; }
.field label { display: block; margin-bottom: 3px; }
.field-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.network-list {
  max-height: 220px; overflow-y: auto; border: 1px solid var(--border); border-radius: 4px;
  font-family: 'Consolas', 'Courier New', monospace; font-size: 12px;
}
.network-item {
  padding: 6px 8px; cursor: pointer; border-bottom: 1px solid var(--border); transition: .1s;
  display: flex; justify-content: space-between; align-items: center;
}
.network-item:last-child { border-bottom: none; }
.network-item:hover { background: rgba(88,166,255,.08); }
.network-item.selected { background: rgba(88,166,255,.15); border-left: 3px solid var(--accent); }
.network-item .bssid { color: var(--accent); }
.network-item .essid { color: var(--text); }
.network-item .meta { color: var(--text-dim); font-size: 11px; }
.network-item.vuln { border-left: 3px solid var(--orange); }
.radio-group { display: flex; gap: 16px; flex-wrap: wrap; }
.radio-group label { display: flex; align-items: center; gap: 4px; cursor: pointer; }
.checkbox-group { display: flex; flex-wrap: wrap; gap: 8px 16px; }
.checkbox-group label { display: flex; align-items: center; gap: 4px; cursor: pointer; font-size: 13px; }
.log-box {
  background: #000; border: 1px solid var(--border); border-radius: var(--radius);
  font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; line-height: 1.5;
  height: 280px; overflow-y: auto; padding: 8px; white-space: pre-wrap; word-break: break-all;
}
.log-box .ts { color: var(--text-dim); }
.log-box .info { color: var(--green); }
.log-box .warn { color: var(--orange); }
.log-box .err { color: var(--red); }
.ctrl-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 8px; }
.pin-row { display: flex; gap: 8px; align-items: center; }
.pin-row input { flex: 1; font-family: monospace; letter-spacing: 2px; }
.modal {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,.7); z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.modal-content {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); max-width: 780px; width: 94%;
  max-height: 85vh; display: flex; flex-direction: column;
  box-shadow: 0 8px 32px rgba(0,0,0,.5);
}
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
}
.modal-header h2 { font-size: 16px; margin: 0; }
.modal-body { padding: 0; overflow-y: auto; flex: 1; }
.modal-body table {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
.modal-body th {
  position: sticky; top: 0; background: var(--surface);
  padding: 8px 10px; text-align: left; border-bottom: 2px solid var(--border);
  color: var(--text-dim); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
}
.modal-body td {
  padding: 7px 10px; border-bottom: 1px solid var(--border);
  max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.modal-body tr:hover td { background: rgba(88,166,255,.05); }
.modal-body .psk-cell { font-family: monospace; color: var(--green); letter-spacing: 0.5px; }
.modal-body .pin-cell { font-family: monospace; color: var(--accent); }
.modal-body .empty-msg { text-align: center; padding: 30px; color: var(--text-dim); font-size: 14px; }
.modal-footer {
  display: flex; gap: 8px; justify-content: flex-end;
  padding: 12px 16px; border-top: 1px solid var(--border);
}
@media (max-width: 600px) {
  .col { min-width: 100%; }
  .header { flex-direction: column; align-items: stretch; }
  .radio-group { gap: 8px; }
}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1><span>&#9762;</span> OPX OneShot <span style="font-size:11px;color:var(--text-dim);font-weight:normal">v0.0.2 by OP AMINUL FF</span></h1>
    <div class="iface-group">
      <label for="iface">Interface</label>
      <select id="iface"></select>
      <button class="btn" onclick="refreshIfaces()">&#8635;</button>
    </div>
  </div>

  <div class="row">
    <div class="col">
      <div class="card">
        <div class="card-title">Target Network</div>
        <button class="btn btn-primary" id="scanBtn" onclick="startScan()">&#128269; Scan</button>
        <div class="network-list" id="netList"><div style="padding:8px;color:var(--text-dim);font-size:13px">Click Scan to discover networks</div></div>
        <div class="field" style="margin-top:8px">
          <label>BSSID</label>
          <input id="bssid" placeholder="e.g. 00:90:4C:C1:AC:21" spellcheck="false">
        </div>
      </div>
      <div class="card">
        <div class="card-title">PIN</div>
        <div class="pin-row">
          <input id="pin" placeholder="Enter PIN or leave empty" spellcheck="false">
          <button class="btn" onclick="generatePin()">Generate</button>
        </div>
      </div>
    </div>

    <div class="col">
      <div class="card">
        <div class="card-title">Attack Mode</div>
        <div class="radio-group">
          <label><input type="radio" name="mode" value="pixie" checked> Pixie Dust</label>
          <label><input type="radio" name="mode" value="bruteforce"> Bruteforce</label>
          <label><input type="radio" name="mode" value="pbc"> PBC</label>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Options</div>
        <div class="checkbox-group">
          <label><input type="checkbox" id="opt_write"> Write Creds</label>
          <label><input type="checkbox" id="opt_force"> Pixie Force</label>
          <label><input type="checkbox" id="opt_show_cmd"> Show Cmd</label>
          <label><input type="checkbox" id="opt_loop"> Loop</label>
          <label><input type="checkbox" id="opt_reverse"> Reverse</label>
          <label><input type="checkbox" id="opt_verbose"> Verbose</label>
          <label><input type="checkbox" id="opt_iface_down"> Iface Down</label>
          <label><input type="checkbox" id="opt_mtk"> MTK WiFi</label>
        </div>
        <div class="field-row" style="margin-top:8px;gap:12px">
          <div style="display:flex;align-items:center;gap:4px"><label>Delay</label><input id="delay" type="number" value="0" min="0" style="width:60px"> <span style="font-size:12px;color:var(--text-dim)">sec</span></div>
          <div style="display:flex;align-items:center;gap:4px;flex:1"><label>Vuln List</label><input id="vuln_list" placeholder="vulnwsc.txt" style="flex:1"></div>
        </div>
      </div>
      <div class="ctrl-row">
        <button class="btn btn-success" id="startBtn" onclick="startAttack()">&#9654; Start Attack</button>
        <button class="btn btn-danger" id="stopBtn" onclick="stopAttack()" disabled>&#9632; Stop</button>
        <button class="btn" onclick="showHistory()">&#128203; History</button>
        <button class="btn" onclick="clearLog()">Clear Log</button>
        <span id="statusBadge" style="font-size:12px;color:var(--text-dim)">Ready</span>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Output</div>
    <div class="log-box" id="logBox"></div>
  </div>
</div>

<div id="historyModal" class="modal" style="display:none">
  <div class="modal-content">
    <div class="modal-header">
      <h2>&#128203; WiFi History</h2>
      <button class="btn" onclick="closeHistory()" style="font-size:18px;padding:2px 10px">&times;</button>
    </div>
    <div class="modal-body" id="historyBody">
      <div style="text-align:center;padding:20px;color:var(--text-dim)">Loading...</div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-danger" onclick="clearHistory()">&#128465; Clear All</button>
      <button class="btn" onclick="closeHistory()">Close</button>
    </div>
  </div>
</div>

<script>
let eventSource = null;
let attackRunning = false;
let selectedBssid = '';

function log(msg, cls='info') {
  const box = document.getElementById('logBox');
  const t = new Date().toLocaleTimeString();
  box.innerHTML += `<span class="ts">[${t}]</span> <span class="${cls}">${escapeHtml(msg)}</span>\n`;
  box.scrollTop = box.scrollHeight;
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function refreshIfaces() {
  fetch('/api/interfaces').then(r=>r.json()).then(data => {
    const sel = document.getElementById('iface');
    const current = sel.value;
    sel.innerHTML = data.map(i => `<option value="${i}">${i}</option>`).join('');
    if (data.includes(current)) sel.value = current;
  });
}

function startScan() {
  const iface = document.getElementById('iface').value;
  const vuln = document.getElementById('vuln_list').value;
  const rev = document.getElementById('opt_reverse').checked;
  document.getElementById('netList').innerHTML = '<div style="padding:8px;color:var(--orange);font-size:13px">Scanning...</div>';
  document.getElementById('scanBtn').disabled = true;
  fetch(`/api/scan?interface=${encodeURIComponent(iface)}&vuln_list=${encodeURIComponent(vuln)}&reverse=${rev}`);
}

function loadNetworks() {
  fetch('/api/networks').then(r=>r.json()).then(data => {
    const list = document.getElementById('netList');
    if (!data.length) {
      list.innerHTML = '<div style="padding:8px;color:var(--text-dim);font-size:13px">No networks found</div>';
      return;
    }
    list.innerHTML = data.map((n,i) => {
      const cls = n.vuln ? 'network-item vuln' : 'network-item';
      return `<div class="${cls}" onclick="selectNet(${i},'${n.bssid}')">
        <div><span class="bssid">${n.bssid}</span> <span class="essid">${escapeHtml(n.essid)}</span></div>
        <div class="meta">CH${n.channel} ${n.signal}dBm ${n.wps?'WPS':''}${n.vuln?' [VULN]':''}</div>
      </div>`;
    }).join('');
  });
}

function selectNet(i, bssid) {
  selectedBssid = bssid;
  document.getElementById('bssid').value = bssid;
  document.querySelectorAll('.network-item').forEach((el,idx) => el.classList.toggle('selected', idx===i));
}

function generatePin() {
  const bssid = document.getElementById('bssid').value;
  if (!bssid) { log('Enter BSSID first', 'warn'); return; }
  fetch(`/api/generate_pin?bssid=${encodeURIComponent(bssid)}`).then(r=>r.json()).then(data => {
    if (data.pin) { document.getElementById('pin').value = data.pin; log(`Generated PIN: ${data.pin}`); }
    else if (data.error) log(`PIN error: ${data.error}`, 'err');
  });
}

function getParams() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  return {
    iface: document.getElementById('iface').value,
    bssid: document.getElementById('bssid').value,
    pin: document.getElementById('pin').value,
    delay: parseInt(document.getElementById('delay').value) || 0,
    write: document.getElementById('opt_write').checked,
    pixie: mode === 'pixie',
    bruteforce: mode === 'bruteforce',
    pbc: mode === 'pbc',
    force: document.getElementById('opt_force').checked,
    show_cmd: document.getElementById('opt_show_cmd').checked,
    loop: document.getElementById('opt_loop').checked,
    reverse: document.getElementById('opt_reverse').checked,
    verbose: document.getElementById('opt_verbose').checked,
    iface_down: document.getElementById('opt_iface_down').checked,
    mtk: document.getElementById('opt_mtk').checked,
    vuln_list: document.getElementById('vuln_list').value,
  };
}

function startAttack() {
  if (attackRunning) return;
  const params = getParams();
  if (!params.iface) { log('Select interface', 'warn'); return; }
  fetch('/api/attack', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(params)})
  .then(r=>r.json()).then(d => {
    if (d.error) { log(d.error, 'err'); return; }
    attackRunning = true;
    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled = false;
    document.getElementById('statusBadge').textContent = 'Attack running...';
    log('[*] Attack started', 'info');
  });
}

function stopAttack() {
  fetch('/api/stop').then(() => {
    attackRunning = false;
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
    document.getElementById('statusBadge').textContent = 'Stopped';
    log('[!] Attack stopped by user', 'warn');
  });
}

function clearLog() {
  document.getElementById('logBox').innerHTML = '';
}

function connectSSE() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource('/stream');
  eventSource.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data);
      log(escapeHtml(d.msg));
    } catch(_) {}
  };
  eventSource.addEventListener('done', (e) => {
    const d = JSON.parse(e.data);
    if (d.msg === '__SCAN_DONE__') {
      document.getElementById('scanBtn').disabled = false;
      document.getElementById('statusBadge').textContent = 'Scan complete';
      loadNetworks();
      log('[+] Scan finished', 'info');
    } else if (d.msg === '__ATTACK_DONE__') {
      attackRunning = false;
      document.getElementById('startBtn').disabled = false;
      document.getElementById('stopBtn').disabled = true;
      document.getElementById('statusBadge').textContent = 'Attack finished';
    }
  });
  eventSource.onerror = () => setTimeout(connectSSE, 1000);
}

function showHistory() {
  const body = document.getElementById('historyBody');
  body.innerHTML = '<div class="empty-msg">Loading...</div>';
  document.getElementById('historyModal').style.display = 'flex';
  fetch('/api/history').then(r=>r.json()).then(data => {
    if (!data || !data.length) {
      body.innerHTML = '<div class="empty-msg">No history yet. Successful attacks will appear here.</div>';
      return;
    }
    let html = '<table><thead><tr><th>#</th><th>WiFi</th><th>BSSID</th><th>PIN</th><th>Password</th><th>Mode</th><th>Date</th></tr></thead><tbody>';
    data.slice().reverse().forEach((e,i) => {
      html += `<tr>
        <td style="color:var(--text-dim)">${data.length-i}</td>
        <td><b>${escapeHtml(e.essid || '-')}</b></td>
        <td style="font-family:monospace;font-size:12px;color:var(--accent)">${escapeHtml(e.bssid || '-')}</td>
        <td class="pin-cell">${escapeHtml(e.pin || '-')}</td>
        <td class="psk-cell">${e.psk ? escapeHtml(e.psk) : '<span style="color:var(--text-dim)">-</span>'}</td>
        <td style="font-size:12px"><span style="background:var(--bg);padding:2px 6px;border-radius:3px;border:1px solid var(--border)">${escapeHtml(e.mode)}</span></td>
        <td style="font-size:11px;color:var(--text-dim)">${escapeHtml(e.timestamp)}</td>
      </tr>`;
    });
    html += '</tbody></table>';
    body.innerHTML = html;
  }).catch(() => {
    body.innerHTML = '<div class="empty-msg">Error loading history</div>';
  });
}

function closeHistory() {
  document.getElementById('historyModal').style.display = 'none';
}

function clearHistory() {
  if (!confirm('Clear all saved passwords?')) return;
  fetch('/api/history/clear', {method:'POST'}).then(r=>r.json()).then(d => {
    if (d.status === 'ok') {
      document.getElementById('historyBody').innerHTML = '<div class="empty-msg">History cleared.</div>';
      log('[+] History cleared', 'info');
    }
  });
}

refreshIfaces();
setInterval(refreshIfaces, 5000);
connectSSE();
</script>
<div style="text-align:center;padding:12px 0 4px;font-size:11px;color:var(--text-dim);border-top:1px solid var(--border);margin-top:12px">
  <b>OPX OneShot</b> — by <a href="https://github.com/OP-AMINUL-FF" style="color:var(--accent);text-decoration:none">OP AMINUL FF</a>
  &nbsp;|&nbsp; <a href="https://opaminulff.vercel.app/" style="color:var(--accent);text-decoration:none" target="_blank">Website</a>
  &nbsp;|&nbsp; <a href="https://github.com/OP-AMINUL-FF/opx-oneshot" style="color:var(--accent);text-decoration:none" target="_blank">GitHub</a>
</div>
</body>
</html>'''

# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ('-u', '--update', 'update'):
        import subprocess as _sp
        _dir = os.path.dirname(os.path.abspath(__file__))
        print(f"[*] Updating OneShot in {_dir}...")
        r = _sp.run(['git', 'pull'], cwd=_dir, capture_output=True, text=True)
        print(r.stdout + r.stderr)
        sys.exit(0 if r.returncode == 0 else 1)

    if os.geteuid() != 0:
        print("[-] Root privileges required. Run with sudo.")
        sys.exit(1)

    try:
        port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    except ValueError:
        print("[-] Invalid port: {}".format(sys.argv[1]))
        sys.exit(1)
    ip = get_own_ip()
    print(f"[*] OPX OneShot WebUI — by OP AMINUL FF")
    print(f"[*] Website: https://opaminulff.vercel.app")
    print(f"[*] Local:   http://127.0.0.1:{port}")
    print(f"[*] Network: http://{ip}:{port}")
    print(f"[*] Press Ctrl+C to stop")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
