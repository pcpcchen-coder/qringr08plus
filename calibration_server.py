"""Loopback-only R08 calibration bridge. Never posts mouse events."""
import argparse
import asyncio
import json
import math
import os
import struct
import time
from pathlib import Path
from aiohttp import web
from ring_mouse import find_ring, BleakClient, WRITE, NOTIFY, pack, profile_axes

ROOT=Path(__file__).parent
PROFILE=ROOT/'calibration.json'
peers=set()
task=None
stop=asyncio.Event()
state={'type':'status','connected':False,'message':'尚未連線'}

async def publish(data):
    for ws in list(peers):
        try: await ws.send_json(data)
        except Exception: peers.discard(ws)

async def status(connected,message):
    global state
    state={'type':'status','connected':connected,'message':message}
    await publish(state)

async def session():
    await status(False,'正在連接戒指…')
    try:
        device=await find_ring('R08_E703')
        if device is None: raise RuntimeError('找不到戒指，請確認手機 QRing 斷線、戒指已充電並靠近 Mac。')
        async with BleakClient(device,timeout=20) as client:
            queue=asyncio.Queue()
            arrived=asyncio.Event()
            pending=set()
            def emit(data):
                t=asyncio.create_task(publish(data));pending.add(t);t.add_done_callback(pending.discard)
            def notify(_,data):
                f=bytes(data)
                if len(f)!=16 or sum(f[:15])&255!=f[15]: return
                if f[0]==0x3b: queue.put_nowait(f)
                if f[:2]==b'\xa1\x03':
                    arrived.set();emit({'type':'accel','raw':list(struct.unpack('>hhh',f[2:8]))})
                if f[:2]==b'\x73\x2d': emit({'type':'gesture','code':f[2]})
            await client.start_notify(NOTIFY,notify)
            for u in ['00002a27-0000-1000-8000-00805f9b34fb','00002a26-0000-1000-8000-00805f9b34fb']:
                await client.read_gatt_char(u)
            await asyncio.sleep(.5)
            async def cmd(payload):
                while not queue.empty(): queue.get_nowait()
                await client.write_gatt_char(WRITE,pack(0x3b,payload),response=False)
                try: return await asyncio.wait_for(queue.get(),3)
                except asyncio.TimeoutError: return None
            original=await cmd(b'\x01\x00')
            if original is None or original[1]!=1: raise RuntimeError('無法讀取原設定，請重新連接。')
            try:
                if await cmd(b'\x01\x00\x01\x01') is None: raise RuntimeError('戒指沒有接受觸控啟用。')
                await asyncio.sleep(.5)
                if await cmd(b'\x02\x00\x09\x01') is None: raise RuntimeError('戒指沒有接受手勢回報設定。')
                await status(True,'R08 已連線')
                while not stop.is_set():
                    arrived.clear()
                    await client.write_gatt_char(WRITE,pack(0xa1,b'\x03'),response=False)
                    try: await asyncio.wait_for(arrived.wait(),.3)
                    except asyncio.TimeoutError: pass
                    await asyncio.sleep(.06)
            finally:
                if client.is_connected:
                    await client.write_gatt_char(WRITE,pack(0xa1,b'\x00'),response=False)
                    await asyncio.sleep(.4)
                    await cmd(bytes([2,0,original[3],original[4]]))
                    if original[2]: await cmd(b'\x01\x00\x01\x00')
                    result=await cmd(b'\x01\x00')
                    if result is None or result[1:5]!=original[1:5]:
                        raise RuntimeError('連線已結束，但無法確認設定還原，請回 QRing 檢查。')
                if pending: await asyncio.gather(*pending,return_exceptions=True)
        await status(False,'已中斷連線，原設定已還原。')
    except Exception as e:
        await status(False,str(e))

@web.middleware
async def guard(request,handler):
    if request.host not in ('127.0.0.1:8765','localhost:8765'): raise web.HTTPForbidden()
    origin=request.headers.get('Origin')
    if origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765'): raise web.HTTPForbidden()
    if request.method=='POST' and request.content_type!='application/json': raise web.HTTPUnsupportedMediaType()
    return await handler(request)

async def connect(request):
    global task
    if task is None or task.done():
        stop.clear();task=asyncio.create_task(session())
    return web.json_response({'ok':True})

async def disconnect(request):
    stop.set()
    if task and not task.done(): await task
    return web.json_response({'ok':True,'message':state['message']})

async def ws(request):
    socket=web.WebSocketResponse(heartbeat=20)
    await socket.prepare(request);peers.add(socket)
    await socket.send_json(state)
    try:
        async for _ in socket: pass
    finally: peers.discard(socket)
    return socket

async def save(request):
    try:
        data=await request.json()
        profile_axes(data)
        if data.get('name')!='R08_E703': raise ValueError('戒指名稱不符')
        speed=float(data['speed'])
        if not math.isfinite(speed) or not 60<=speed<=500: raise ValueError('速度超出範圍')
        clean={'version':1,'name':'R08_E703','poses':data['poses'],'speed':speed}
        temporary=PROFILE.with_suffix('.tmp')
        temporary.write_text(json.dumps(clean,indent=2));os.replace(temporary,PROFILE)
        return web.json_response({'ok':True})
    except (ValueError,KeyError,TypeError) as e: return web.json_response({'error':str(e)},status=400)

async def profile(request):
    return web.json_response({'profile':json.loads(PROFILE.read_text()) if PROFILE.exists() else None})

async def cleanup(app):
    stop.set()
    if task and not task.done(): await task
    for socket in list(peers): await socket.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--web-root',default=str(ROOT/'web'));args=parser.parse_args()
    root=Path(args.web_root)
    app=web.Application(middlewares=[guard],client_max_size=16384)
    app.router.add_post('/api/connect',connect);app.router.add_post('/api/disconnect',disconnect)
    app.router.add_post('/api/save',save);app.router.add_get('/api/profile',profile);app.router.add_get('/ws',ws)
    app.router.add_get('/',lambda r:web.FileResponse(root/'index.html'));app.router.add_static('/',root)
    app.on_cleanup.append(cleanup)
    print('校正工具：http://127.0.0.1:8765',flush=True)
    web.run_app(app,host='127.0.0.1',port=8765)
