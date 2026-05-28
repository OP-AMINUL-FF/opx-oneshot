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
    # Method 1: /proc/net/dev (most reliable on Termux/Android)
    try:
        with open('/proc/net/dev') as f:
            for line in f.readlines()[2:]:
                iface = line.strip().split(':')[0].strip()
                if iface not in seen:
                    ifaces.append(iface)
                    seen.add(iface)
    except:
        pass
    # Method 2: iw dev (refine with wireless-capable interfaces)
    try:
        r = subprocess.run(['iw', 'dev'], capture_output=True, text=True)
        for line in r.stdout.split('\n'):
            if 'Interface' in line:
                iface = line.split()[-1]
                if iface not in seen:
                    ifaces.append(iface)
                    seen.add(iface)
    except:
        pass
    # Method 3: iwconfig (catch any remaining interfaces)
    try:
        r = subprocess.run(['iwconfig'], capture_output=True, text=True)
        for line in r.stdout.split('\n'):
            sline = line.strip()
            if sline and ' ' in line and not line.startswith((' ', '\t')):
                iface = line.split()[0].strip()
                # Skip non-interface lines
                if iface.lower() not in skip_words and not iface.startswith('('):
                    if iface not in seen:
                        ifaces.append(iface)
                        seen.add(iface)
    except:
        pass
    # Filter out non-wireless virtual interfaces (lo, tunnels) but keep everything
    # that might be a Wi-Fi interface
    return ifaces if ifaces else ['wlan0']

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
    with LogCapture():
        try:
            if not ifaceUp(iface):
                print(f"[-] Failed to bring up {iface}")
                return
            path = vuln_path or os.path.join(os.path.dirname(os.path.realpath(__file__)), 'vulnwsc.txt')
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    current_vuln_list = f.read().splitlines()
            except:
                current_vuln_list = []
        except:
            current_vuln_list = []
        try:
            scanner = WiFiScanner(iface, current_vuln_list)
            result = scanner.iw_scanner()
            scan_results = list(result.values()) if result else []
        except Exception as e:
            print(f"[-] Scan error: {e}")
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

    with LogCapture():
        try:
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
                try:
                    if stop_event.is_set():
                        print("[!] Attack stopped by user")
                        break

                    oneshot.args.loop = loop
                    companion = Companion(iface, write, print_debug=verbose)
                    current_companion = companion

                    if pbc:
                        companion.single_connection(pbc_mode=True)
                    elif bruteforce:
                        companion.smart_bruteforce(bssid, pin, delay)
                    else:
                        companion.single_connection(bssid, pin, pixie, False,
                                                    show_cmd, pixie_force)

                    if not loop:
                        break
                except KeyboardInterrupt:
                    if loop:
                        print("[?] Continuing loop...")
                        continue
                    else:
                        print("\n[!] Aborting…")
                        break
        except Exception as e:
            print(f"[-] Attack error: {e}")
        finally:
            if iface_down:
                ifaceUp(iface, down=True)
            if mtk:
                try:
                    wmt.write_text('0')
                except:
                    pass
            attack_running = False
            current_companion = None

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
<title>OneShot WebUI</title>
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
    <h1><span>&#9762;</span> OneShot WebUI</h1>
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

refreshIfaces();
setInterval(refreshIfaces, 5000);
connectSSE();
</script>
</body>
</html>'''

# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    if os.geteuid() != 0:
        print("[-] Root privileges required. Run with sudo.")
        sys.exit(1)

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    ip = get_own_ip()
    print(f"[*] OneShot WebUI started")
    print(f"[*] Local:   http://127.0.0.1:{port}")
    print(f"[*] Network: http://{ip}:{port}")
    print(f"[*] Press Ctrl+C to stop")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
