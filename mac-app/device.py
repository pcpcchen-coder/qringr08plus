import asyncio
import json
import math
import os
import struct
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from ring_mouse import BleakClient, Controller, find_ring, pack, profile_axes, WRITE, NOTIFY, Q

SOURCE='https://github.com/MRziyi/Halo-Ring/blob/main/Doc/09-r08-ble-protocol-spec.md'
MEASUREMENTS={1:('hr','心率','bpm'),3:('spo2','血氧','%'),2:('bp','血壓',''),4:('fatigue','疲勞',''),5:('composite','綜合檢查',''),6:('realtime_hr','即時心率',''),7:('ecg','心電圖',''),8:('stress','壓力',''),9:('glucose','血糖',''),10:('hrv','HRV',''),11:('temperature','體溫','')}
SAFE_READS={
 'battery':(3,b''),'capabilities':(0x3c,b''),'notification_routes':(0x61,b''),'touch_settings':(0x3b,b'\x01\x00'),
 'hr_auto':(0x16,b'\x01'),'spo2_auto':(0x2c,b'\x01'),'stress_auto':(0x36,b'\x01'),'hrv_auto':(0x38,b'\x01'),
 'bp_auto':(0x0c,b'\x01'),'temperature_auto':(0x3a,b'\x03\x01'),'personal_profile':(0x0a,b'\x01'),
 'temperature_unit':(0x19,b'\x01'),'targets':(0x21,b'\x01'),'sedentary':(0x26,b''),
 'drink_reminder':(0x28,b'\x00'),'today_activity':(0x48,b''),'hr_history':(0x15,b'\x00'),
 'hrv_history':(0x39,b'\x00'),'stress_history':(0x37,b'\x00'),'steps_history':(0x43,b'\x00'),
 'sleep_history':(0x44,b'\x00'),'data_days':(0x46,b'\x00'),'bp_history':(0x14,b'\x00'),
 'power_saving':(0x76,b'\x00'),'ping':(0x18,b''),'hardware_alt':(0x93,b''),
 'ecg_settings':(0x6c,b'\x01'),'gesture_wake':(0x05,b'\x03'),'display_wake':(0x12,b'\x01')}

class Device:
    def __init__(self,folder):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.profile_path=self.folder/'calibration.json'
        self.catalog=json.loads((Path(__file__).parent/'catalog.json').read_text())
        self.client=None;self.task=None;self.stop=asyncio.Event();self.lock=asyncio.Lock();self.measure_lock=asyncio.Lock()
        self.waiter=None;self.active=None;self.measure_done=asyncio.Event();self.samples=asyncio.Event();self.touch_original=None;self.auto_original={}
        self.touch_on=False;self.other_notifications=set();self.control=Controller();self.peers=set();self.records=deque(maxlen=1000);self.evidence={};self.options={k:False for k in ('mouse','click','accel','touch','hr','spo2','battery','calibration','raw_gatt')}
        self.options.update(health_interval=120,accel_interval=.15,manage_auto=True)
        self.state={'connected':False,'message':'尚未連線','name':'R08_E703','battery':None,'charging':None,'hardware':None,'firmware':None,'values':{},'options':self.options,'paused':True,'auto_status':'未讀取','access':Q.CGPreflightPostEventAccess(),'gatt':[]}
        self.log_path=self.folder/('session-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.jsonl')
        self.log_file=self.log_path.open('a',buffering=1)
        self.pending=set();self.other_failed=set();self.last_gesture=0;self.channels={};self.next_health={};self.next_battery=0;self.last_poll=0
    def log(self,direction,**fields):
        row={'time':datetime.now().astimezone().isoformat(),'direction':direction,**fields}
        self.records.append(row);self.log_file.write(json.dumps(row,ensure_ascii=False)+'\n')
        return row
    def emit(self,data):
        async def send():
            for ws in list(self.peers):
                try: await ws.send_json(data)
                except Exception:self.peers.discard(ws)
        t=asyncio.create_task(send());self.pending.add(t);t.add_done_callback(self.pending.discard)
    def status(self,connected,message):
        self.state.update(connected=connected,message=message)
        self.log('系統',message=message);self.emit({'type':'status','connected':connected,'message':message})
    def snapshot(self):
        self.state.update(paused=self.control.paused,access=Q.CGPreflightPostEventAccess(),calibrated=self.profile_path.exists(),active_measurement=self.active,channels=self.channels)
        return {**self.state,'evidence':self.evidence,'catalog':self.catalog,'read_queries':[{'key':k,'opcode':f'{v[0]:02X}','payload':v[1].hex(' ')} for k,v in SAFE_READS.items()],'logs':list(self.records),'log_file':self.log_path.name}
    def notify(self,char,data):
        f=bytes(data);valid=len(f)==16 and sum(f[:15])&255==f[15]
        self.log('RX',characteristic=str(char.uuid),hex=f.hex(' '),checksum=valid)
        if str(char.uuid).lower()!=NOTIFY:return
        if not valid:return
        op=f[0]
        if self.waiter and not self.waiter[1].done() and op in (self.waiter[0],self.waiter[0]|128):self.waiter[1].set_result(f)
        if op==3 and f[1]<=100:self.state.update(battery=f[1],charging=bool(f[2]));self.evidence['battery']='實機回報'
        if op==0x3c:self.state['capabilities']=list(f[2:11]);self.evidence['capabilities']='實機回報'
        if op==0xa1:
            channel=f[1];self.channels[str(channel)]=self.channels.get(str(channel),0)+1
            if channel==3:
                raw=list(struct.unpack('>hhh',f[2:8]));self.state['values']['accel']={'raw':raw,'nominal_g':[round(x/8192,4) for x in raw],'time':datetime.now().astimezone().isoformat()}
                self.control.update(raw,time.monotonic());self.samples.set();self.evidence['accel']='實機回報';self.emit({'type':'accel','raw':raw})
        if op==0x73:
            sub=f[1];self.state['last_notification']={'sub':sub,'payload':list(f[2:15])}
            if sub==0x2d:
                code=f[2];self.evidence['touch']='實機回報';self.state['values']['gesture']={'code':code,'name':{1:'上滑',2:'下滑',3:'單擊',4:'長按'}.get(code,'未知'),'time':datetime.now().astimezone().isoformat()};self.emit({'type':'gesture','code':code})
                now=time.monotonic()
                if now-self.last_gesture>.5:
                    self.last_gesture=now
                    if code==4 and self.options['mouse']:
                        self.control.paused=not self.control.paused;self.control.velocity=(0.,0.);self.log('系統',message='滑鼠暫停' if self.control.paused else '滑鼠移動啟用')
                    if code==3 and self.options['mouse'] and self.options['click'] and self.active is None and not self.control.paused and now-self.control.last<.35 and Q.CGPreflightPostEventAccess():
                        p=Q.CGEventGetLocation(Q.CGEventCreate(None))
                        for typ in (Q.kCGEventLeftMouseDown,Q.kCGEventLeftMouseUp):Q.CGEventPost(Q.kCGHIDEventTap,Q.CGEventCreateMouseEvent(None,typ,p,Q.kCGMouseButtonLeft))
                        self.log('輸出',message='左鍵點擊')
        if op==0x69:
            typ,err,value=f[1],f[2],f[3]
            feature=MEASUREMENTS.get(typ,('unknown','',''))[0]
            result={'type':typ,'error':err,'value':value,'raw_payload':list(f[1:15]),'time':datetime.now().astimezone().isoformat()}
            if typ in (1,3) and err==0 and value>0:
                result['display']=f'{value} {MEASUREMENTS[typ][2]}';self.evidence[feature]='實機有效值回報（準確度未驗證）';self.measure_done.set()
            elif err==2:result['display']='配戴接觸不良';self.evidence[feature]='有回應／配戴失敗';self.measure_done.set()
            elif err==1:result['display']='完成訊號，無已解碼有效值';self.evidence[feature]='回報完成訊號';self.measure_done.set()
            else:result['display']='量測中／未收斂';self.evidence[feature]='有回應，尚無有效值'
            self.state['values'][feature]=result
        if op<0x80 and op not in (3,0x3c,0x69,0x73):self.state['values'][f'op_{op:02x}']={'hex':f.hex(' '),'time':datetime.now().astimezone().isoformat()}
    async def send(self,op,payload=b'',reply=True,timeout=2):
        async with self.lock:
            if not self.client or not self.client.is_connected:raise RuntimeError('戒指未連線')
            future=asyncio.get_running_loop().create_future();self.waiter=(op,future) if reply else None
            f=pack(op,payload);self.log('TX',opcode=f'{op:02X}',hex=f.hex(' '))
            try:
                await self.client.write_gatt_char(WRITE,f,response=False)
                if not reply:return None
                try:return await asyncio.wait_for(future,timeout)
                except asyncio.TimeoutError:self.log('系統',opcode=f'{op:02X}',message='等待回應逾時');return None
            finally:self.waiter=None
    async def read_feature(self,key):
        if key not in SAFE_READS:raise ValueError('不在允許的唯讀查詢清單')
        op,payload=SAFE_READS[key];f=await self.send(op,payload)
        verdict='無回應' if f is None else ('裝置拒絕／不支援' if f[0]==(op|128) and f[1]==0xee else '實機回報（內容待解碼）')
        self.evidence[key]=verdict;self.log('解析',feature=key,status=verdict,hex=f.hex(' ') if f else '')
        return {'feature':key,'status':verdict,'hex':f.hex(' ') if f else None}
    async def connect(self):
        if self.task and not self.task.done():return
        self.stop.clear();self.task=asyncio.create_task(self.run())
    async def disconnect(self):
        self.options.update(mouse=False,click=False,accel=False,touch=False,hr=False,spo2=False,battery=False,calibration=False)
        self.control.paused=True;self.stop.set();self.measure_done.set()
        if self.measure_lock.locked():
            async with self.measure_lock:pass
        if self.task and not self.task.done():await self.task
    async def touch(self,enable):
        if enable==self.touch_on:return
        if enable:
            if not self.touch_original:
                f=await self.send(0x3b,b'\x01\x00')
                if f is None or f[0]!=0x3b or f[1]!=1:raise RuntimeError('無法備份觸控設定')
                self.touch_original=f
            a=await self.send(0x3b,b'\x01\x00\x01\x01');await asyncio.sleep(.5)
            b=await self.send(0x3b,b'\x02\x00\x09\x01')
            if a is None or b is None or a[0]!=0x3b or b[0]!=0x3b:raise RuntimeError('無法啟用觸控')
        elif self.touch_original:
            f=self.touch_original;await self.send(0x3b,bytes([2,0,f[3],f[4]]))
            if f[2]:await self.send(0x3b,b'\x01\x00\x01\x00')
            after=await self.send(0x3b,b'\x01\x00')
            self.log('還原',feature='touch',verified=after is not None and after[1:5]==f[1:5])
        self.touch_on=enable
    async def manage_auto(self,enable):
        issues=[]
        for key,op in [('hr_auto',0x16),('spo2_auto',0x2c),('stress_auto',0x36),('hrv_auto',0x38)]:
            if enable:
                f=await self.send(op,b'\x01')
                if f is None or f[0]!=op or f[1]!=1:issues.append(key);continue
                self.auto_original[op]=f
                if op==0x16:payload=bytes([2,0,f[3],f[4],f[6],f[5],0])
                elif op==0x2c:payload=bytes([2,0,f[3]])
                else:payload=b'\x02\x00'
                await self.send(op,payload);check=await self.send(op,b'\x01')
                verified=check is not None and check[0]==op and check[2]==0
                self.log('排程',feature=key,disabled_verified=verified)
                if not verified:issues.append(key)
            elif op in self.auto_original:
                f=self.auto_original[op]
                if op==0x16:payload=bytes([2,f[2],f[3],f[4],f[6],f[5],f[7]])
                elif op==0x2c:payload=bytes([2,f[2],f[3]])
                else:payload=bytes([2,f[2]])
                await self.send(op,payload);check=await self.send(op,b'\x01')
                fields=(2,3,4,5,6,7) if op==0x16 else ((2,3) if op==0x2c else (2,))
                verified=check is not None and check[0]==op and all(check[i]==f[i] for i in fields)
                self.log('還原',feature=key,verified=verified)
                if not verified:issues.append(key)
        self.state['auto_status']=('部分排程未確認：'+', '.join(issues)) if issues else ('心率／血氧／壓力／HRV 內建排程已暫停；血壓／體溫等未接管' if enable else '已還原內建排程')
        if not enable:self.auto_original={}
    async def set_options(self,changes):
        allowed=set(self.options)
        if set(changes)-allowed:raise ValueError('未知選項')
        opts={**self.options,**changes}
        for key in ('mouse','click','accel','touch','hr','spo2','battery','calibration','raw_gatt','manage_auto'):
            if not isinstance(opts[key],bool):raise ValueError('選項必須是勾選值')
        if not 60<=float(opts['health_interval'])<=3600 or not .1<=float(opts['accel_interval'])<=2:raise ValueError('讀取間隔超出範圍')
        if opts['calibration']:opts['mouse']=False;opts['click']=False
        if opts['mouse']:
            if not self.profile_path.exists():raise ValueError('請先完成五步校正並儲存')
            if not Q.CGPreflightPostEventAccess():raise ValueError('請在系統設定的裝置控制和資料取用授權 QRing Studio')
            p=json.loads(self.profile_path.read_text());self.control.axes=profile_axes(p);self.control.limit=p['speed']
            if not self.options['mouse']:self.control.paused=True
        else:self.control.paused=True;opts['click']=False
        previous=self.options.copy();self.options.update(opts)
        if previous['manage_auto']!=opts['manage_auto'] and self.state['connected']:await self.manage_auto(opts['manage_auto'])
        if self.active and not self.options.get(MEASUREMENTS[self.active][0],False):self.measure_done.set()
        self.log('選項',options=self.options.copy())
    async def measure(self,typ,manual=False,timeout=40):
        if typ not in MEASUREMENTS or typ==7:raise ValueError('本版未提供未確認的 ECG 啟動流程')
        if self.measure_lock.locked():raise ValueError('另一項量測正在進行')
        async with self.measure_lock:
            self.active=typ;self.measure_done.clear();key=MEASUREMENTS[typ][0]
            self.log('量測',feature=key,message='開始單次量測' if manual else '勾選項目的排程量測')
            try:
                await self.send(0x69,bytes([typ,1]),reply=False)
                started=time.monotonic()
                while not self.stop.is_set() and time.monotonic()-started<timeout:
                    if not manual and not self.options.get(key,False):break
                    try:await asyncio.wait_for(self.measure_done.wait(),.4);break
                    except asyncio.TimeoutError:pass
                result=self.state['values'].get(key)
                if not result or result.get('time','')<datetime.fromtimestamp(time.time()-(time.monotonic()-started)).astimezone().isoformat():
                    self.evidence[key]='本次無有效回報'
                return result
            finally:
                try:
                    if self.client and self.client.is_connected:await self.send(0x6a,bytes([typ,4,0]),timeout=2)
                except Exception as e:self.log('錯誤',feature=key,message='停止量測時連線已中斷：'+str(e))
                self.active=None;self.next_health[key]=time.monotonic()+self.options['health_interval']
                self.log('量測',feature=key,message='已送停止指令；不保證所有韌體回覆停止 ACK')
    async def scheduler(self):
        while not self.stop.is_set():
            now=time.monotonic()
            if self.options['battery'] and now>=self.next_battery:await self.read_feature('battery');self.next_battery=now+60
            if self.active is None:
                for typ,key in ((1,'hr'),(3,'spo2')):
                    if self.options[key] and now>=self.next_health.get(key,0):await self.measure(typ);break
            await asyncio.sleep(.3)
    async def polling(self):
        had_accel=False
        while not self.stop.is_set():
            want=self.options['accel'] or self.options['mouse'] or self.options['calibration']
            want_touch=self.options['touch'] or self.options['mouse'] or self.options['calibration']
            if want_touch!=self.touch_on:await self.touch(want_touch)
            if self.options['raw_gatt']:
                for service in self.client.services:
                    for char in service.characteristics:
                        if char.uuid!=NOTIFY and char.uuid not in self.other_notifications and char.uuid not in self.other_failed and ('notify' in char.properties or 'indicate' in char.properties):
                            try:await self.client.start_notify(char,self.notify);self.other_notifications.add(char.uuid);self.log('訂閱',characteristic=char.uuid)
                            except Exception as e:self.other_failed.add(char.uuid);self.log('錯誤',characteristic=char.uuid,message=str(e))
            elif self.other_notifications:
                for uuid in list(self.other_notifications):
                    await self.client.stop_notify(uuid);self.other_notifications.remove(uuid);self.log('取消訂閱',characteristic=uuid)
            if not self.options['raw_gatt']:self.other_failed.clear()
            if want and self.active is None:
                self.samples.clear();await self.send(0xa1,b'\x03',reply=False)
                try:await asyncio.wait_for(self.samples.wait(),.35)
                except asyncio.TimeoutError:pass
                had_accel=True;await asyncio.sleep(self.options['accel_interval'])
            else:
                if had_accel:await self.send(0xa1,b'\x00',reply=False);had_accel=False
                self.control.velocity=(0.,0.);await asyncio.sleep(.15)
    async def movement(self):
        last=time.monotonic();last_log=0
        while not self.stop.is_set():
            now=time.monotonic();dt=min(.04,now-last);last=now
            if self.options['mouse'] and self.active is None and Q.CGPreflightPostEventAccess():
                vx,vy=self.control.current(now)
                if vx or vy:
                    p=Q.CGEventGetLocation(Q.CGEventCreate(None));b=Q.CGDisplayBounds(Q.CGMainDisplayID())
                    target=(max(b.origin.x,min(b.origin.x+b.size.width-1,p.x+vx*dt)),max(b.origin.y,min(b.origin.y+b.size.height-1,p.y+vy*dt)))
                    Q.CGEventPost(Q.kCGHIDEventTap,Q.CGEventCreateMouseEvent(None,Q.kCGEventMouseMoved,target,Q.kCGMouseButtonLeft))
                    if now-last_log>.5:self.log('輸出',message='系統游標移動',velocity=[round(vx,1),round(vy,1)]);last_log=now
            await asyncio.sleep(1/60)
    async def run(self):
        self.status(False,'正在尋找戒指…')
        workers=[]
        try:
            device=await find_ring(self.state['name'])
            if device is None:raise RuntimeError('找不到戒指，請讓手機 QRing 斷線')
            async with BleakClient(device,timeout=20) as client:
                self.client=client;await client.start_notify(NOTIFY,self.notify)
                for key,u in [('hardware','00002a27-0000-1000-8000-00805f9b34fb'),('firmware','00002a26-0000-1000-8000-00805f9b34fb'),('serial','00002a25-0000-1000-8000-00805f9b34fb')]:
                    value=bytes(await client.read_gatt_char(u)).decode(errors='replace');self.state[key]=value;self.log('GATT',field=key,value=value)
                self.state['gatt']=[{'service':s.uuid,'description':s.description,'characteristics':[{'uuid':c.uuid,'properties':c.properties} for c in s.characteristics]} for s in client.services]
                report=json.loads((Path(__file__).parent/'verified-device.json').read_text())
                if report['device']==self.state['name'] and report['hardware']==self.state['hardware'] and report['firmware']==self.state['firmware']:
                    for key,value in report['features'].items():self.evidence.setdefault(key,'既有實測（'+report['date']+'）：'+value)
                self.log('GATT',services=self.state['gatt']);await asyncio.sleep(.5)
                try:
                    await self.read_feature('battery');await self.read_feature('capabilities')
                    if self.options['manage_auto']:await self.manage_auto(True)
                    self.status(True,'已連線；未勾選的 App 量測不會啟動')
                    workers=[asyncio.create_task(fn()) for fn in (self.polling,self.scheduler,self.movement)]
                    stopper=asyncio.create_task(self.stop.wait())
                    done,_=await asyncio.wait(workers+[stopper],return_when=asyncio.FIRST_COMPLETED)
                    stopper.cancel()
                    for worker in done:
                        if worker in workers:await worker
                finally:
                    self.stop.set();self.control.paused=True
                    for w in workers:w.cancel()
                    await asyncio.gather(*workers,return_exceptions=True)
                    if client.is_connected:
                        if self.active:await self.send(0x6a,bytes([self.active,4,0]),timeout=2)
                        await self.send(0xa1,b'\x00',reply=False)
                        if self.touch_on:await self.touch(False)
                        if self.auto_original:await self.manage_auto(False)
                    self.touch_original=None;self.touch_on=False;self.active=None;self.other_notifications.clear()
            self.status(False,'已中斷，停止 App 量測並嘗試還原內建設定')
        except Exception as e:self.status(False,str(e));self.log('錯誤',message=str(e))
        finally:self.client=None;self.options.update(mouse=False,click=False,accel=False,touch=False,hr=False,spo2=False,battery=False,calibration=False,raw_gatt=False)
