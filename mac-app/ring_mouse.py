"""R08 tilt mouse prototype. Starts paused; long press toggles movement."""
import argparse
import asyncio
import json
import math
import signal
import statistics
import struct
import time
from datetime import datetime
from pathlib import Path

import Quartz as Q
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.corebluetooth.CentralManagerDelegate import CentralManagerDelegate
from CoreBluetooth import CBUUID

WRITE = '6e400002-b5a3-f393-e0a9-e50e24dcca9e'
NOTIFY = '6e400003-b5a3-f393-e0a9-e50e24dcca9e'

def pack(op, payload=b''):
    if len(payload)>14:
        raise ValueError('Payload too long')
    frame=(bytes([op])+payload).ljust(15,b'\0')
    return frame+bytes([sum(frame)&255])

def unit(v):
    norm=math.sqrt(sum(x*x for x in v))
    if norm<1:
        raise ValueError('Invalid gravity vector')
    return tuple(x/norm for x in v)

def dot(a,b):
    return sum(x*y for x,y in zip(a,b))

def basis(neutral):
    g=unit(neutral)
    reference=(1,0,0) if abs(g[0])<.9 else (0,1,0)
    projection=dot(reference,g)
    right=unit(tuple((reference[i]-projection*g[i])*8192 for i in range(3)))
    up=(g[1]*right[2]-g[2]*right[1],g[2]*right[0]-g[0]*right[2],g[0]*right[1]-g[1]*right[0])
    return g,right,up

def profile_axes(profile):
    if profile.get('version') not in (1,2):
        raise ValueError('不支援的校正版本')
    poses=profile.get('poses')
    expected=5 if profile.get('version')==2 else 3
    if not isinstance(poses,list) or len(poses)!=expected:
        raise ValueError('需要中立與版本指定的所有方向姿勢')
    for pose in poses:
        if not isinstance(pose,list) or len(pose)!=3 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in pose):
            raise ValueError('姿勢資料無效')
        if not .9<=math.sqrt(sum(x*x for x in pose))<=1.1:
            raise ValueError('姿勢向量無效')
    n=unit(tuple(x*8192 for x in poses[0]))
    tangents=[]
    for pose in poses[1:]:
        g=unit(tuple(x*8192 for x in pose))
        d=dot(g,n)
        if d>math.cos(math.radians(8)) or d<.5:
            raise ValueError('請使用約 10–60 度的傾斜姿勢')
        tangents.append(unit(tuple((x-d*n[i])*8192 for i,x in enumerate(g))))
    if expected==5:
        rr,ll,uu,dd=tangents
        if dot(rr,ll)>-.2 or dot(uu,dd)>-.2:
            raise ValueError('右／左或上／下姿勢不是相反方向')
        r=unit(tuple((rr[i]-ll[i])*8192 for i in range(3)))
        u=unit(tuple((uu[i]-dd[i])*8192 for i in range(3)))
    else:
        r,u=tangents
    c=dot(r,u)
    den=1-c*c
    if den<.2:
        raise ValueError('向右與向上姿勢太接近')
    return n,tuple((r[i]-c*u[i])/den for i in range(3)),tuple((u[i]-c*r[i])/den for i in range(3))

def speed(angle,limit):
    dead=math.radians(8)
    amount=max(0,min(1,(abs(angle)-dead)/math.radians(27)))
    return math.copysign(limit*amount*amount,angle)

class Controller:
    def __init__(self,limit=220,invert_x=False,invert_y=False):
        self.limit=limit
        self.sx=-1 if invert_x else 1
        self.sy=1 if invert_y else -1
        self.axes=None
        self.velocity=(0.,0.)
        self.last=0.
        self.paused=True
    def calibrate(self,samples):
        self.axes=basis(tuple(statistics.mean(v[i] for v in samples) for i in range(3)))
        self.velocity=(0.,0.)
    def update(self,raw,now):
        norm=math.sqrt(sum(x*x for x in raw))/8192
        self.last=now
        if self.axes is None or not .8<=norm<=1.2:
            self.velocity=(0.,0.)
            return
        g=unit(raw)
        neutral,right,up=self.axes
        denom=dot(g,neutral)
        if denom<.5:
            self.velocity=(0.,0.)
            return
        target=(self.sx*speed(math.atan2(dot(g,right),denom),self.limit),
                self.sy*speed(math.atan2(dot(g,up),denom),self.limit))
        self.velocity=tuple(.4*old+.6*new for old,new in zip(self.velocity,target))
    def current(self,now):
        return (0.,0.) if self.paused or now-self.last>.35 else self.velocity

async def find_ring(name):
    manager=CentralManagerDelegate.alloc().init()
    ps=manager.central_manager.retrieveConnectedPeripheralsWithServices_(
        [CBUUID.UUIDWithString_('1812'),CBUUID.UUIDWithString_('6e40fff0-b5a3-f393-e0a9-e50e24dcca9e')])
    for p in ps:
        if str(p.name())==name:
            return BLEDevice(str(p.identifier().UUIDString()),name,(p,manager))
    return await BleakScanner.find_device_by_filter(lambda d,a:(a.local_name or d.name)==name,timeout=15)

async def run(args):
    if not args.dry_run and not Q.CGPreflightPostEventAccess():
        print('NEEDS_ACCESSIBILITY: Enable Accessibility for the app running this program. No mouse events sent.',flush=True)
        return 2
    records=[]
    def log(kind,**fields):
        row=dict(time=datetime.now().astimezone().isoformat(),kind=kind,**fields)
        records.append(row)
        if kind not in ('accel','notify'):
            print(json.dumps(row,ensure_ascii=False),flush=True)
    saved=None
    path=Path(__file__).parent/'calibration.json'
    if path.exists() and not args.ignore_calibration:
        saved=json.loads(path.read_text())
        if saved.get('name')!=args.name:
            raise ValueError('校正檔的戒指名稱不符')
        axes=profile_axes(saved)
        log('saved_calibration_loaded',speed=saved['speed'])
    controller=Controller(args.speed or (saved['speed'] if saved else 220),args.invert_x,args.invert_y)
    if saved: controller.axes=axes
    stop=asyncio.Event()
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        loop.add_signal_handler(sig,stop.set)
    device=await find_ring(args.name)
    if device is None:
        print('RING_NOT_FOUND',flush=True)
        return 1
    try:
        async with BleakClient(device,timeout=20) as client:
            queue=asyncio.Queue()
            samples=[]
            sample_event=asyncio.Event()
            last_gesture=[0.]
            def notify(_,data):
                frame=bytes(data)
                if len(frame)!=16 or sum(frame[:15])&255!=frame[15]:
                    log('invalid_notify',hex=frame.hex(' '))
                    return
                log('notify',hex=frame.hex(' '))
                queue.put_nowait(frame)
                if frame[:2]==b'\xa1\x03':
                    raw=struct.unpack('>hhh',frame[2:8])
                    now=time.monotonic()
                    samples.append((now,raw))
                    controller.update(raw,now)
                    sample_event.set()
                    log('accel',raw=raw)
                if frame[:2]==b'\x73\x2d':
                    now=time.monotonic()
                    code=frame[2]
                    if now-last_gesture[0]<.4:
                        return
                    last_gesture[0]=now
                    log('gesture',code=code)
                    if code==4 and controller.axes is not None:
                        controller.paused=not controller.paused
                        controller.velocity=(0.,0.)
                        log('paused',value=controller.paused)
                    elif code==3 and args.click and not controller.paused and controller.axes is not None and now-controller.last<=.35:
                        log('click',dry_run=args.dry_run)
                        if not args.dry_run:
                            position=Q.CGEventGetLocation(Q.CGEventCreate(None))
                            for event_type in (Q.kCGEventLeftMouseDown,Q.kCGEventLeftMouseUp):
                                Q.CGEventPost(Q.kCGHIDEventTap,Q.CGEventCreateMouseEvent(None,event_type,position,Q.kCGMouseButtonLeft))
            await client.start_notify(NOTIFY,notify)
            for label,u in [('hardware','00002a27-0000-1000-8000-00805f9b34fb'),('firmware','00002a26-0000-1000-8000-00805f9b34fb')]:
                log(label,value=bytes(await client.read_gatt_char(u)).decode(errors='replace'))
            await asyncio.sleep(.5)
            async def command(op,payload=b''):
                while not queue.empty(): queue.get_nowait()
                frame=pack(op,payload)
                log('send',hex=frame.hex(' '))
                await client.write_gatt_char(WRITE,frame,response=False)
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    try: response=await asyncio.wait_for(queue.get(),deadline-time.monotonic())
                    except asyncio.TimeoutError: break
                    if response[0]==op: return response
                return None
            original=await command(0x3b,b'\x01\x00')
            if original is None or original[1]!=1:
                raise RuntimeError('Cannot read original touch settings; no touch changes made')
            try:
                if await command(0x3b,b'\x01\x00\x01\x01') is None:
                    raise RuntimeError('Touch enable not acknowledged')
                await asyncio.sleep(.5)
                if await command(0x3b,b'\x02\x00\x09\x01') is None:
                    raise RuntimeError('Gesture reporting not acknowledged')
                if not saved: log('hold_still',seconds=3)
                async def poll():
                    while not stop.is_set():
                        sample_event.clear()
                        await client.write_gatt_char(WRITE,pack(0xa1,b'\x03'),response=False)
                        try: await asyncio.wait_for(sample_event.wait(),.3)
                        except asyncio.TimeoutError: pass
                        await asyncio.sleep(.06)
                polling=asyncio.create_task(poll())
                async def move():
                    previous=time.monotonic()
                    while not stop.is_set():
                        now=time.monotonic()
                        dt=min(.04,now-previous)
                        previous=now
                        vx,vy=controller.current(now)
                        if (vx or vy) and not args.dry_run:
                            p=Q.CGEventGetLocation(Q.CGEventCreate(None))
                            bounds=Q.CGDisplayBounds(Q.CGMainDisplayID())
                            x=max(bounds.origin.x,min(bounds.origin.x+bounds.size.width-1,p.x+vx*dt))
                            y=max(bounds.origin.y,min(bounds.origin.y+bounds.size.height-1,p.y+vy*dt))
                            Q.CGEventPost(Q.kCGHIDEventTap,Q.CGEventCreateMouseEvent(None,Q.kCGEventMouseMoved,(x,y),Q.kCGMouseButtonLeft))
                        await asyncio.sleep(1/60)
                moving=asyncio.create_task(move())
                try:
                    deadline=time.monotonic()+20
                    while controller.axes is None and not stop.is_set() and time.monotonic()<deadline:
                        if polling.done():
                            await polling
                        await asyncio.sleep(.2)
                        recent=[raw for stamp,raw in samples if stamp>=time.monotonic()-3]
                        if len(recent)>=12 and samples[-1][0]-samples[-len(recent)][0]>=2.5:
                            normalized=[unit(v) for v in recent]
                            spread=max(statistics.pstdev(v[i] for v in normalized) for i in range(3))
                            valid_norms=all(.8<=math.sqrt(sum(x*x for x in raw))/8192<=1.2 for raw in recent)
                            if spread<.025 and valid_norms:
                                controller.calibrate(recent)
                                log('calibrated',samples=len(recent),spread=spread)
                    if controller.axes is None:
                        raise RuntimeError('Calibration failed: hold still for 3 seconds and retry')
                    log('ready',dry_run=args.dry_run,starts_paused=True,click_enabled=args.click,seconds=args.seconds)
                    waiter=asyncio.create_task(stop.wait())
                    done,_=await asyncio.wait((waiter,polling,moving),timeout=args.seconds,return_when=asyncio.FIRST_COMPLETED)
                    waiter.cancel()
                    for task in done:
                        if task in (polling,moving): await task
                    stop.set()
                    log('summary',accel_samples=len(samples),gestures=sum(r['kind']=='gesture' for r in records))
                finally:
                    stop.set()
                    for task in (polling,moving): task.cancel()
                    await asyncio.gather(polling,moving,return_exceptions=True)
                    controller.paused=True
            finally:
                if client.is_connected:
                    frame=pack(0xa1,b'\x00')
                    await client.write_gatt_char(WRITE,frame,response=False)
                    await asyncio.sleep(.4)
                    await command(0x3b,bytes([2,0,original[3],original[4]]))
                    if original[2]: await command(0x3b,b'\x01\x00\x01\x00')
                    restored=await command(0x3b,b'\x01\x00')
                    log('restore_check',matches_original=restored is not None and restored[1:5]==original[1:5])
    finally:
        folder=Path(__file__).parent/'logs'
        folder.mkdir(exist_ok=True)
        path=folder/('mouse-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
        path.write_text(json.dumps(records,ensure_ascii=False,indent=2))
        print('LOG_SAVED',path,flush=True)
    return 0

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',default='R08_E703')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--click',action='store_true')
    parser.add_argument('--seconds',type=float,default=60)
    parser.add_argument('--speed',type=float,default=None)
    parser.add_argument('--ignore-calibration',action='store_true')
    parser.add_argument('--invert-x',action='store_true')
    parser.add_argument('--invert-y',action='store_true')
    args=parser.parse_args()
    if (args.speed is not None and not 1<=args.speed<=600) or not 1<=args.seconds<=3600: parser.error('Invalid speed or duration')
    raise SystemExit(asyncio.run(run(args)))
