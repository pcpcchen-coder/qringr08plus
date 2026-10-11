"""Build the Apple Silicon app using active Apple Python and project dependencies."""
import os
import plistlib
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
OUTPUT=PROJECT/'releases'/'.build.noindex'
APP=OUTPUT/'QRing Studio.app'
FRAMEWORK=Path(sys.base_prefix).resolve().parents[1]
SITE=Path(sysconfig.get_path('purelib'))

if __name__=='__main__':
    if sys.version_info[:2] != (3,9):
        raise SystemExit('Build with the project Python 3.9 venv; the native launcher requires Python 3.9.')
    if FRAMEWORK.name != 'Python3.framework' or not (FRAMEWORK/'Versions/3.9/bin/python3.9').is_file():
        raise SystemExit('An Apple Python3.framework is required (Xcode or Command Line Tools).')
    if sys.prefix == sys.base_prefix or not (SITE/'aiohttp').is_dir() or not (SITE/'bleak').is_dir():
        raise SystemExit('Run with the project .venv after installing requirements.txt.')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    if APP.exists():shutil.rmtree(APP)
    mac=APP/'Contents/MacOS';mac.mkdir(parents=True)
    resources=APP/'Contents/Resources';resources.mkdir()
    framework=APP/'Contents/Frameworks/Python3.framework'
    shutil.copytree(FRAMEWORK,framework,symlinks=True)
    shutil.copytree(SITE,resources/'site-packages',ignore=shutil.ignore_patterns('__pycache__','pip','pip-*.dist-info','setuptools','setuptools-*.dist-info','pkg_resources','wheel','wheel-*.dist-info'))
    appcode=resources/'app';appcode.mkdir()
    for file in ('server.py','device.py','ring_mouse.py','catalog.json','verified-device.json'):
        shutil.copy2(ROOT/file,appcode/file)
    shutil.copytree(ROOT/'web',appcode/'web')
    info={'CFBundleIdentifier':'com.pcpcchen.qringstudio','CFBundleName':'QRing Studio','CFBundleDisplayName':'QRing Studio','CFBundleExecutable':'QRingStudio','CFBundlePackageType':'APPL','CFBundleShortVersionString':'0.3.0','CFBundleVersion':'3','LSMinimumSystemVersion':'13.0','NSHighResolutionCapable':True,'NSBluetoothAlwaysUsageDescription':'連接你的 QRing 戒指，讀取勾選的感測資料與觸控事件。','NSBluetoothPeripheralUsageDescription':'連接你的 QRing 戒指。','NSAppTransportSecurity':{'NSAllowsLocalNetworking':True}}
    (APP/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    subprocess.run(['swiftc','-O','-target','arm64-apple-macosx13.0','-framework','Cocoa','-framework','WebKit',str(ROOT/'native/Studio.swift'),'-o',str(mac/'QRingStudio')],check=True)
    subprocess.run(['codesign','--force','--deep','--sign','-',str(APP)],check=True)
    subprocess.run(['codesign','--verify','--deep','--strict',str(APP)],check=True)
    print(APP)
