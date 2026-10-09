import argparse
import asyncio
import json
import math
import os
import secrets
from pathlib import Path
from aiohttp import web
from device import Device,MEASUREMENTS,SAFE_READS,profile_axes,Q

async def create_app(folder,port):
    engine=Device(folder)
    tasks=set()
    @web.middleware
    async def guard(req,handler):
        if req.host not in (f'127.0.0.1:{port}',f'localhost:{port}'):raise web.HTTPForbidden()
        origin=req.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):raise web.HTTPForbidden()
        if req.method=='POST' and req.content_type!='application/json':raise web.HTTPUnsupportedMediaType()
        try:return await handler(req)
        except (ValueError,KeyError,TypeError,RuntimeError) as e:return web.json_response({'error':str(e)},status=400)
    app=web.Application(middlewares=[guard],client_max_size=32768)
    app['engine']=engine
    async def state(req):return web.json_response(engine.snapshot())
    async def connect(req):await engine.connect();return web.json_response({'ok':True})
    async def disconnect(req):await engine.disconnect();return web.json_response({'ok':True,'message':engine.state['message']})
    async def options(req):await engine.set_options(await req.json());return web.json_response({'ok':True})
    async def read(req):
        data=await req.json();return web.json_response(await engine.read_feature(data['feature']))
    async def pause(req):
        engine.control.paused=True;engine.control.velocity=(0.,0.);engine.log('系統',message='手動暫停滑鼠');return web.json_response({'ok':True})
    async def request_access(req):
        allowed=Q.CGRequestPostEventAccess()
        return web.json_response({'ok':True,'allowed':bool(allowed)})
    async def measure(req):
        data=await req.json();typ=int(data['type'])
        if typ not in MEASUREMENTS or typ==7:raise ValueError('不支援這個量測探測流程')
        if not engine.state['connected']:raise ValueError('請先連接戒指')
        if engine.measure_lock.locked():raise ValueError('另一項量測正在進行')
        async def job():
            try:await engine.measure(typ,manual=True,timeout=40)
            except Exception as e:engine.log('錯誤',message=str(e))
        t=asyncio.create_task(job());tasks.add(t);t.add_done_callback(tasks.discard)
        return web.json_response({'ok':True})
    async def profile(req):return web.json_response({'profile':json.loads(engine.profile_path.read_text()) if engine.profile_path.exists() else None})
    async def save(req):
        data=await req.json();profile_axes(data);speed=float(data['speed'])
        if data.get('name')!=engine.state['name'] or not math.isfinite(speed) or not 60<=speed<=500:raise ValueError('校正名稱或速度無效')
        clean={k:data[k] for k in ('version','name','poses','speed')};p=engine.profile_path.with_suffix('.tmp');p.write_text(json.dumps(clean,indent=2));os.replace(p,engine.profile_path)
        engine.log('校正',message='校正設定已儲存');return web.json_response({'ok':True})
    async def ws(req):
        sock=web.WebSocketResponse(heartbeat=20);await sock.prepare(req);engine.peers.add(sock)
        await sock.send_json({'type':'status','connected':engine.state['connected'],'message':engine.state['message']})
        try:
            async for _ in sock:pass
        finally:engine.peers.discard(sock)
        return sock
    async def export(req):
        engine.log_file.flush()
        return web.FileResponse(engine.log_path,headers={'Content-Disposition':'attachment; filename="qring-session.jsonl"'})
    async def shutdown(req):
        await engine.disconnect();app['shutdown'].set();return web.json_response({'ok':True})
    app['shutdown']=asyncio.Event()
    for path,handler in [('/api/state',state),('/api/profile',profile),('/api/export',export),('/ws',ws)]:app.router.add_get(path,handler)
    for path,handler in [('/api/connect',connect),('/api/disconnect',disconnect),('/api/options',options),('/api/read',read),('/api/pause',pause),('/api/measure',measure),('/api/save',save),('/api/request-access',request_access),('/api/shutdown',shutdown)]:app.router.add_post(path,handler)
    root=Path(__file__).parent/'web'
    async def index(req):return web.FileResponse(root/'index.html',headers={'Cache-Control':'no-store'})
    app.router.add_get('/',index);app.router.add_static('/',root)
    async def cleanup(app):
        for t in tasks:t.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        await engine.disconnect()
        for ws in list(engine.peers):await ws.close()
        if engine.pending:await asyncio.gather(*engine.pending,return_exceptions=True)
        engine.log_file.close()
    app.on_cleanup.append(cleanup)
    return app

async def main(args):
    app=await create_app(args.data_dir,args.port)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',args.port);await site.start()
    print(f'READY http://127.0.0.1:{args.port}',flush=True)
    try:await app['shutdown'].wait()
    finally:await runner.cleanup()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18765);parser.add_argument('--data-dir',default=str(Path.home()/'Library'/'Application Support'/'QRing Studio'));args=parser.parse_args()
    try:asyncio.run(main(args))
    except KeyboardInterrupt:pass
