<div align="center">

# ⚡ OPX OneShot

### by **OP AMINUL FF**

**Pixie Dust WPS Attack — No Monitor Mode Required**

[![Kali](https://img.shields.io/badge/Kali-557C94?style=for-the-badge&logo=kalilinux&logoColor=white&labelColor=2A2A2A)](https://www.kali.org/)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-E95420?style=for-the-badge&logo=ubuntu&logoColor=white&labelColor=2A2A2A)](https://ubuntu.com/)
[![Arch](https://img.shields.io/badge/Arch-1793D1?style=for-the-badge&logo=archlinux&logoColor=white&labelColor=2A2A2A)](https://archlinux.org/)
[![Fedora](https://img.shields.io/badge/Fedora-51A2DA?style=for-the-badge&logo=fedora&logoColor=white&labelColor=2A2A2A)](https://fedoraproject.org/)
[![Termux](https://img.shields.io/badge/Termux-000000?style=for-the-badge&logo=terminal&logoColor=white&labelColor=2A2A2A)](https://termux.com/)

[![Developer](https://img.shields.io/badge/Developer-OP%20AMINUL%20FF-ff6600?style=flat-square&logo=github&labelColor=1a1a2e)](https://github.com/OP-AMINUL-FF)
[![Company](https://img.shields.io/badge/Company-OPX-00ccff?style=flat-square&labelColor=1a1a2e)](https://github.com/OP-AMINUL-FF)
[![Website](https://img.shields.io/badge/Website-opaminulff.vercel.app-8B5CF6?style=flat-square&logo=vercel&labelColor=1a1a2e)](https://opaminulff.vercel.app/)
[![Version](https://img.shields.io/github/v/release/OP-AMINUL-FF/opx-oneshot?style=flat-square&color=blue&labelColor=1a1a2e)](https://github.com/OP-AMINUL-FF/opx-oneshot/releases)
[![Stars](https://img.shields.io/github/stars/OP-AMINUL-FF/opx-oneshot?style=flat-square&color=yellow&labelColor=1a1a2e)](https://github.com/OP-AMINUL-FF/opx-oneshot)
[![License](https://img.shields.io/badge/license-GPLv3-green?style=flat-square&labelColor=1a1a2e)](LICENSE)

---

**🔥 4 interfaces · 16 CLI options mapped · Same attack engine · Cross-platform**

**👨‍💻 Developer:** OP AMINUL FF  
**🏢 Company:** OPX  
**🌐 Website:** [https://opaminulff.vercel.app](https://opaminulff.vercel.app/)  
**📦 Tool:** `opx-oneshot`

</div>

---

## 🚀 Quick Install (All Platforms)

```bash
# Download & run installer
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/install.sh
# or: curl -LO https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/install.sh

bash install.sh
```

Then from **anywhere**:

| Command | Action |
|---------|--------|
| `opx-oneshot` | 🚀 Start WebUI at `http://127.0.0.1:5000` |
| `opx-oneshot 8080` | 🔌 Start on custom port |
| `opx-oneshot -u` | 🔄 Update to latest version |
| `opx-oneshot -r` | 🗑️ Remove completely |

> Installer auto-detects your OS, installs **all** dependencies, clones the repo, and creates the global **opx-oneshot** command — usable from anywhere.

---

## 📦 What's Included

| File | Platform | Type | Best For |
|------|----------|------|----------|
| `oneshot_web.py` | **Any** (Linux / Termux / Windows) | 🌐 **WebUI** | Browser on any device |
| `oneshot_gui.py` | Linux Desktop | 🖥️ tkinter GUI | Native desktop experience |
| `oneshot_termux.py` | Termux (Android) | 📱 curses TUI | Terminal-only (no X11) |
| `oneshot.py` | Linux / Termux | ⌨️ CLI | Original command-line tool |
| `install.sh` | **Any** | 📦 Installer | One-command setup |

All four use the **same attack engine** (`Companion` class from `oneshot.py`) with all **16 CLI options** mapped to interactive controls.

---

## ✨ Features

<div align="center">

| | Feature | | Feature |
|---|---|---|---|
| ⚡ | **Pixie Dust** — offline WPS attack | 🔄 | **Loop mode** — auto-repeat |
| 🔨 | **Bruteforce** — online PIN guessing | 🔀 | **Reverse scan** — small displays |
| 🔘 | **PBC** — Push Button Connect | 📢 | **Verbose** — debug output |
| 📡 | **Wi-Fi scanner** — vulnerable device highlight | 📴 | **Iface Down** — auto-cleanup |
| 🔑 | **3WiFi PIN generator** — offline PINs | 📶 | **MTK WiFi** — MediaTek driver |
| 💾 | **Save credentials** on success | 📋 | **Custom vuln list** — `--vuln-list` |
| ⏱️ | **Delay control** between attempts | 🛑 | **Stop anytime** — clean exit |

</div>

---

## 🌐 WebUI — Same UI Everywhere

**Single interface that works identically on Linux, Kali, and Termux.**  
Runs a local web server — open in **any browser** (Chrome, Firefox, Kiwi, etc.).

### Install

<details>
<summary><b>📘 Debian / Kali / Ubuntu</b></summary>

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-wcwidth python3-flask \
                     wpasupplicant pixiewps iw wireless-tools iproute2
```
</details>

<details>
<summary><b>📗 Arch Linux</b></summary>

```bash
sudo pacman -S python python-pip python-flask python-wcwidth \
               wpa_supplicant pixiewps iw wireless_tools iproute2
```
</details>

<details>
<summary><b>📕 Fedora</b></summary>

```bash
sudo dnf install -y python3 python3-pip python3-flask python3-wcwidth \
                     wpa_supplicant pixiewps iw wireless-tools iproute
```
</details>

<details>
<summary><b>📱 Termux</b></summary>

```bash
pkg update
pkg install -y root-repo
pkg install -y tsu python wpa-supplicant pixiewps iw openssl \
                iproute2 wireless-tools binutils
pip install flask wcwidth
```
</details>

### Run

```bash
# Linux / Kali
sudo python3 oneshot_web.py

# Termux
sudo python oneshot_web.py
# or: tsu -c "cd ~/opx-oneshot && python oneshot_web.py"
```

### Access

```
http://127.0.0.1:5000        # Same device
http://<your-ip>:5000        # Another device on same network
```

### WebUI Controls

| Control | Description |
|---------|-------------|
| 📡 **Interface** | Dropdown with auto-refresh |
| 🔍 **Scan** | Scans & lists networks with vuln highlight |
| 🎯 **BSSID** | Click a network or type manually |
| 🔑 **PIN** | Manual input + 3WiFi Generate button |
| ⚙️ **Mode** | Radio: Pixie Dust / Bruteforce / PBC |
| ☑️ **Options** | Write, Force, Show Cmd, Loop, Reverse, Verbose, Iface Down, MTK |
| ⏱️ **Delay** | Seconds between PIN attempts |
| 📋 **Vuln List** | Custom vulnerable-devices path |
| ▶️ **Start / Stop** | With status indicator |
| 📜 **Log** | Scrollable real-time console via SSE |

---

## 🖥️ Linux Desktop (tkinter GUI)

```bash
sudo apt install -y python3 python3-pip python3-tk python3-wcwidth python3-flask \
                     wpasupplicant pixiewps iw wireless-tools iproute2
git clone https://github.com/OP-AMINUL-FF/opx-oneshot.git
cd opx-oneshot
sudo python3 oneshot_gui.py
```

> Requires a desktop environment with X11/Wayland.

---

## 📱 Termux (curses TUI)

> **No X11 required.** Runs entirely inside the terminal.

```bash
pkg update
pkg install -y root-repo
pkg install -y git tsu python wpa-supplicant pixiewps iw openssl \
                iproute2 wireless-tools binutils
pip install flask wcwidth
git clone https://github.com/OP-AMINUL-FF/opx-oneshot.git
cd opx-oneshot
sudo python oneshot_termux.py
```

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate |
| `Enter` | Select |
| `Tab` | Switch fields |
| `Space` | Toggle |
| `Esc` / `q` | Quit |

---

## ⌨️ Original CLI (`oneshot.py`)

<details>
<summary><b>Install per platform</b></summary>

**Debian/Kali:**
```bash
sudo apt install -y python3 python3-pip python3-wcwidth python3-flask \
                     wpasupplicant pixiewps iw wireless-tools iproute2
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/oneshot.py
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/vulnwsc.txt
```

**Arch:**
```bash
sudo pacman -S wpa_supplicant pixiewps iw wireless_tools iproute2 python python-pip
pip install wcwidth
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/oneshot.py
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/vulnwsc.txt
```

**Fedora:**
```bash
sudo dnf install -y wpa_supplicant pixiewps iw wireless-tools iproute python3 python3-pip
pip3 install wcwidth
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/oneshot.py
wget https://raw.githubusercontent.com/OP-AMINUL-FF/opx-oneshot/main/vulnwsc.txt
```

**Termux:**
```bash
pkg install -y root-repo
pkg install -y git tsu python wpa-supplicant pixiewps iw openssl \
                iproute2 wireless-tools binutils
pip install wcwidth
git clone --depth 1 https://github.com/OP-AMINUL-FF/opx-oneshot.git
cd opx-oneshot
sudo python oneshot.py -i wlan0 --iface-down -K
```
</details>

### CLI Usage

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

### Examples

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

## ⚠️ Troubleshooting

| Error | Fix |
|-------|-----|
| `RTNETLINK: Operation not possible due to RF-kill` | `sudo rfkill unblock wifi` |
| `Device or resource busy (-16)` | Disable Wi-Fi in system, kill NetworkManager, or use `--iface-down` |
| `wlan0 disappears (MediaTek Android)` | Use `--mtk-wifi` to re-initialize the driver |
| `pip: externally-managed-environment` | Use `python3-flask` via apt (modern Kali/deb) |
| `tsu: Unknown id` | Try `sudo python3 oneshot_web.py` directly |

---

## 📋 Package Reference

| Package | Debian/Kali | Arch | Fedora | Termux |
|---------|-------------|------|--------|--------|
| `wpa_supplicant` | `wpasupplicant` | `wpa_supplicant` | `wpa_supplicant` | `wpa-supplicant` |
| `pixiewps` | `pixiewps` | `pixiewps` | `pixiewps` | `pixiewps` |
| `iw` | `iw` | `iw` | `iw` | `iw` |
| `wireless-tools` | `wireless-tools` | `wireless_tools` | `wireless-tools` | `wireless-tools` |
| `iproute2` | `iproute2` | `iproute2` | `iproute` | `iproute2` |
| `python` | `python3` | `python` | `python3` | `python` |
| `tkinter` | `python3-tk` | `python-tk` | `python3-tkinter` | — (use WebUI) |
| `wcwidth` | `python3-wcwidth` | `python-wcwidth` | `python3-wcwidth` | `pip install` |
| `flask` | `python3-flask` | `python-flask` | `python3-flask` | `pip install` |
| `tsu` | — | — | — | `tsu` |
| `openssl` | *(preinstalled)* | *(preinstalled)* | *(preinstalled)* | `openssl` |
| `binutils` | *(preinstalled)* | *(preinstalled)* | *(preinstalled)* | `binutils` |

> **Just run `bash install.sh`** — it handles all of the above on any platform.

---

## 🙏 Acknowledgements

- **rofl0r** — original OneShot implementation
- **Monohrom** — testing, bug catching, ideas
- **Wiire** — Pixiewps development
- **OP AMINUL FF** — GUI/TUI/WebUI development, cross-platform installer

---

<div align="center">

### 🏢 **OPX** — by **OP AMINUL FF**

**Made with ⚡ for the Wi-Fi security community**

[![Developer](https://img.shields.io/badge/Developer-OP%20AMINUL%20FF-ff6600?style=for-the-badge&logo=github&labelColor=1a1a2e)](https://github.com/OP-AMINUL-FF)
[![Website](https://img.shields.io/badge/Website-opaminulff.vercel.app-8B5CF6?style=for-the-badge&logo=vercel&labelColor=1a1a2e)](https://opaminulff.vercel.app/)
[![Tool](https://img.shields.io/badge/Tool-opx--oneshot-00ccff?style=for-the-badge&logo=git&labelColor=1a1a2e)](https://github.com/OP-AMINUL-FF/opx-oneshot)

```
OPX OneShot — opx-oneshot
Developer  : OP AMINUL FF
Company    : OPX
Website    : https://opaminulff.vercel.app
```

</div>
