# OneShot GUI + TUI

**OneShot** performs [Pixie Dust attack](https://forums.kali.org/showthread.php?24286-WPS-Pixie-Dust-Attack-Offline-WPS-Attack) without having to switch to monitor mode.

This repository includes **four interfaces**:

| File | Platform | Type |
|------|----------|------|
| `oneshot.py` | Linux / Termux | CLI (original) |
| `oneshot_gui.py` | Linux Desktop | tkinter GUI |
| `oneshot_termux.py` | Termux (Android) | curses TUI |
| `oneshot_web.py` | **Any** (Linux, Kali, Termux) | **WebUI** (browser) |

All four support the same 16 CLI options mapped to interactive controls.

---

# Features

- Pixie Dust attack
- Integrated 3WiFi offline WPS PIN generator
- Online WPS bruteforce
- WPS Push Button Connection (PBC)
- Wi-Fi scanner with vulnerable-device highlighting
- Save credentials on success
- Loop mode, reverse scan, verbose output
- MediaTek Wi-Fi driver support (`--mtk-wifi`)
- Custom vulnerable-devices list (`--vuln-list`)

---

# Requirements

- Python 3.6+
- [wpa_supplicant](https://www.w1.fi/wpa_supplicant/)
- [Pixiewps](https://github.com/wiire-a/pixiewps)
- [iw](https://wireless.wiki.kernel.org/en/users/documentation/iw)
- Root access (`sudo`)

---

# Linux Desktop (tkinter GUI)

## Install Dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-tk wpasupplicant pixiewps iw wget
```

## Download

```bash
git clone https://github.com/OP-AMINUL-FF/opx-oneshot.git
cd opx-oneshot
```

Or download just the GUI file:

```bash
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/oneshot_gui.py
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/vulnwsc.txt
```

## Run

```bash
sudo python3 oneshot_gui.py
```

> **Note:** You need a desktop environment with X11/Wayland. Run from a terminal with `sudo`.

## GUI Overview

| Section | Controls |
|---------|----------|
| **Interface** | Dropdown to select Wi-Fi interface |
| **Target** | Scan button + network listbox |
| **Attack Mode** | Pixie Dust, Bruteforce, PBC radio buttons |
| **PIN** | Manual PIN entry + Generate PIN button |
| **Options** | Write creds, Pixie Force, Show Pixie Cmd, Loop, Reverse Scan, Verbose, Iface Down, MTK WiFi |
| **Delay** | Spinbox for pin attempt delay (seconds) |
| **Vuln List** | Load custom vulnerable-devices file |
| **Output** | Scrollable log window |
| **Attack** | Start / Stop buttons |

---

# Termux (curses TUI)

> **No X11 required.** Runs entirely inside the terminal.

## Install Dependencies

```bash
pkg update
pkg install -y root-repo
pkg install -y git tsu python wpa-supplicant pixiewps iw openssl
pip install wcwidth
```

## Download

```bash
git clone https://github.com/OP-AMINUL-FF/opx-oneshot.git
cd opx-oneshot
```

## Run

```bash
sudo python oneshot_termux.py
```

Or with tsu:

```bash
tsu -c "python oneshot_termux.py"
```

## TUI Controls

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate menu items |
| `Enter` | Select / activate |
| `Tab` | Switch between fields |
| `Space` | Toggle checkboxes |
| `Esc` / `q` | Quit / go back |

## TUI Menu Items

All 16 CLI options are mapped:

1. **Interface** — enter interface name (e.g. `wlan0`)
2. **BSSID** — enter target MAC
3. **PIN** — enter custom PIN
4. **Scan** — scan for networks
5. **Pixie Dust** — toggle Pixie Dust attack
6. **Bruteforce** — toggle bruteforce
7. **PBC** — toggle Push Button Connect
8. **Write Creds** — toggle save on success
9. **Pixie Force** — toggle `--force` flag
10. **Show Pixie Cmd** — toggle printing pixiewps command
11. **Delay** — set delay between pins
12. **Loop** — toggle loop mode
13. **Reverse Scan** — toggle reverse order
14. **Verbose** — toggle verbose output
15. **Iface Down** — toggle interface down on exit
16. **MTK WiFi** — toggle MediaTek driver support
17. **Vuln List** — load custom vuln file
18. **Start Attack** — run with current settings

---

# WebUI (`oneshot_web.py`) — Same UI Everywhere

**Single interface that works identically on Linux, Kali, and Termux.**  
Runs a local web server — open in any browser (Chrome, Firefox, Kiwi, etc.).

## Install Dependencies

### Linux / Kali

```bash
sudo apt update
sudo apt install -y python3 python3-pip wpasupplicant pixiewps iw
pip3 install flask
```

### Termux

```bash
pkg update
pkg install -y root-repo
pkg install -y tsu python wpa-supplicant pixiewps iw openssl
pip install flask
```

## Download

```bash
git clone https://github.com/OP-AMINUL-FF/opx-oneshot.git
cd opx-oneshot
```

## Run

### Linux / Kali

```bash
sudo python3 oneshot_web.py
```

### Termux

```bash
sudo python oneshot_web.py
```

Or with `tsu`:

```bash
tsu -c "cd ~/opx-oneshot && python oneshot_web.py"
```

## Access

Open your browser and go to:

```
http://127.0.0.1:5000
```

On Termux (Android), open Chrome/Firefox and navigate to `http://127.0.0.1:5000`.

> **On the same device:** `http://127.0.0.1:5000`  
> **From another device on the same network:** `http://<your-ip>:5000`

## WebUI Features

| Feature | How |
|---------|-----|
| Interface select | Dropdown at top, auto-refreshes |
| Scan | Button + scrollable network list |
| BSSID | Click a network or type manually |
| PIN | Manual input + Generate button (3WiFi) |
| Attack mode | Radio buttons: Pixie Dust / Bruteforce / PBC |
| Options | Checkboxes: Write, Force, Show Cmd, Loop, Reverse, Verbose, Iface Down, MTK |
| Delay | Number input (seconds) |
| Vuln List | Text field for custom path |
| Start / Stop | Buttons with status indicator |
| Log output | Scrollable console, real-time via SSE |

---

# Original CLI (`oneshot.py`)

## Install

### Debian / Ubuntu

```bash
sudo apt install -y python3 wpasupplicant iw pixiewps wget
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/oneshot.py
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/vulnwsc.txt
```

### Arch Linux

```bash
sudo pacman -S wpa_supplicant pixiewps wget python
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/oneshot.py
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/vulnwsc.txt
```

### Termux (CLI only)

```bash
pkg install -y root-repo
pkg install -y git tsu python wpa-supplicant pixiewps iw openssl
git clone --depth 1 https://github.com/OP-AMINUL-FF/opx-oneshot.git
cd opx-oneshot
sudo python oneshot.py -i wlan0 --iface-down -K
```

## Usage

```
oneshot.py <arguments>

Required:
  -i, --interface=<wlan0>   Network interface

Optional:
  -b, --bssid=<mac>         Target AP BSSID
  -p, --pin=<wps pin>       Use specific PIN (4/8 digit or string)
  -K, --pixie-dust          Pixie Dust attack
  -B, --bruteforce          Online bruteforce attack
  --push-button-connect     WPS PBC

Advanced:
  -d, --delay=<n>           Delay between PIN attempts [0]
  -w, --write               Save AP credentials on success
  -F, --pixie-force         Pixiewps --force (bruteforce full range)
  -X, --show-pixie-cmd      Always print pixiewps command
  --vuln-list=<filename>    Custom vulnerable devices list ['vulnwsc.txt']
  --iface-down              Down interface when finished
  -l, --loop                Loop mode
  -r, --reverse-scan        Reverse network order (small displays)
  --mtk-wifi                MediaTek Wi-Fi driver on start/exit
  -v, --verbose             Verbose output
```

## Examples

```bash
# Pixie Dust on specific BSSID
sudo python3 oneshot.py -i wlan0 -b 00:90:4C:C1:AC:21 -K

# Scan + pick network, then Pixie Dust
sudo python3 oneshot.py -i wlan0 -K

# Bruteforce with first half PIN
sudo python3 oneshot.py -i wlan0 -b 00:90:4C:C1:AC:21 -B -p 1234

# Push Button Connect
sudo python3 oneshot.py -i wlan0 --pbc
```

---

# Troubleshooting

#### "RTNETLINK answers: Operation not possible due to RF-kill"

```bash
sudo rfkill unblock wifi
```

#### "Device or resource busy (-16)"

Disable Wi-Fi in system settings, kill NetworkManager, or try `--iface-down`.

#### wlan0 disappears when Wi-Fi is disabled (MediaTek Android)

Use `--mtk-wifi` flag to re-initialize the driver.

---

# Acknowledgements

- `rofl0r` — initial implementation
- `Monohrom` — testing, bug catching, ideas
- `Wiire` — Pixiewps development
