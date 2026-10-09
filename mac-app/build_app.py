"""Build the Apple Silicon app using installed CLT Python and project dependencies."""
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
OUTPUT=PROJECT/'releases'
APP=OUTPUT/'QRing Studio.app'
FRAMEWORK=Path('/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework')
SITE=PROJECT/'.venv/lib/python3.9/site-packages'

if __name__=='__main__':
    OUTPUT.mkdir(exist_ok=True)
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
    info={'CFBundleIdentifier':'com.pcpcchen.qringstudio','CFBundleName':'QRing Studio','CFBundleDisplayName':'QRing Studio','CFBundleExecutable':'QRingStudio','CFBundlePackageType':'APPL','CFBundleShortVersionString':'0.2.0','CFBundleVersion':'2','LSMinimumSystemVersion':'13.0','NSHighResolutionCapable':True,'NSBluetoothAlwaysUsageDescription':'連接你的 QRing 戒指，讀取勾選的感測資料與觸控事件。','NSBluetoothPeripheralUsageDescription':'連接你的 QRing 戒指。','NSAppTransportSecurity':{'NSAllowsLocalNetworking':True}}
    (APP/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    subprocess.run(['swiftc','-O','-target','arm64-apple-macosx13.0','-framework','Cocoa','-framework','WebKit',str(ROOT/'native/Studio.swift'),'-o',str(mac/'QRingStudio')],check=True)
    subprocess.run(['codesign','--force','--deep','--sign','-',str(APP)],check=True)
    subprocess.run(['codesign','--verify','--deep','--strict',str(APP)],check=True)
    print(APP)
