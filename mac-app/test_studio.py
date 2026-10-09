"""Synthetic unit/API tests. No physical health data or mouse events."""
import asyncio
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from aiohttp.test_utils import TestClient,TestServer
from device import Device,pack,NOTIFY,Q
from server import create_app
from ring_mouse import profile_axes,Controller

class DeviceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.device=Device(self.temp.name)
    async def asyncTearDown(self):
        self.device.stop.set();self.device.log_file.close();self.temp.cleanup()
    async def test_idle_never_polls(self):
        d=self.device;calls=[]
        async def send(*args,**kw):calls.append(args)
        d.send=send
        tasks=[asyncio.create_task(d.scheduler()),asyncio.create_task(d.polling())]
        await asyncio.sleep(.35);d.stop.set();await asyncio.gather(*tasks)
        self.assertEqual(calls,[])
        self.assertTrue(all(not d.options[k] for k in ['mouse','click','accel','touch','hr','spo2','battery','raw_gatt']))
    async def test_only_selected_health_schedules(self):
        d=self.device;d.options['hr']=True;calls=[]
        async def measure(typ):calls.append(typ);d.stop.set()
        d.measure=measure;await d.scheduler();self.assertEqual(calls,[1])
    async def test_uncheck_stops_active_measurement(self):
        d=self.device;d.options['hr']=True;sent=[]
        async def send(op,payload=b'',**kw):sent.append((op,payload))
        d.send=send;d.client=SimpleNamespace(is_connected=True)
        task=asyncio.create_task(d.measure(1));await asyncio.sleep(.05)
        await d.set_options({'hr':False});await asyncio.wait_for(task,1)
        self.assertEqual(sent,[(0x69,b'\x01\x01'),(0x6a,b'\x01\x04\x00')]);self.assertIsNone(d.active)
    async def test_mouse_off_never_posts_events(self):
        d=self.device;d.control.paused=False;d.control.velocity=(200,200)
        with patch.object(Q,'CGEventPost') as post:
            task=asyncio.create_task(d.movement());await asyncio.sleep(.07);d.stop.set();await task;post.assert_not_called()
    async def test_invalid_and_secondary_frames_are_logged_not_decoded(self):
        d=self.device;d.notify(SimpleNamespace(uuid=NOTIFY),b'\x03\x64');self.assertIsNone(d.state['battery'])
        d.notify(SimpleNamespace(uuid='other-channel'),pack(3,b'\x64'));self.assertIsNone(d.state['battery']);self.assertEqual(len(d.records),2)
    async def test_four_direction_profile_and_stale_stop(self):
        z=math.sqrt(.75);p={'version':2,'poses':[[0,0,1],[-.5,0,z],[.5,0,z],[0,-.5,z],[0,.5,z]]}
        for raw,axis,sign in [((-4096,0,7094),0,1),((4096,0,7094),0,-1),((0,-4096,7094),1,-1),((0,4096,7094),1,1)]:
            c=Controller();c.axes=profile_axes(p);c.paused=False;c.update(raw,1);self.assertGreater(c.current(1)[axis]*sign,0);self.assertEqual(c.current(1.36),(0,0))

class APITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=await create_app(self.temp.name,18768)
        self.client=TestClient(TestServer(self.app));await self.client.start_server();self.headers={'Host':'127.0.0.1:18768','Origin':'http://127.0.0.1:18768'}
    async def asyncTearDown(self):await self.client.close();self.temp.cleanup()
    async def test_profile_atomic_and_invalid_preserves_previous(self):
        z=math.sqrt(.75);p={'version':2,'name':'R08_E703','speed':220,'poses':[[0,0,1],[-.5,0,z],[.5,0,z],[0,-.5,z],[0,.5,z]]}
        r=await self.client.post('/api/save',json=p,headers=self.headers);self.assertEqual(r.status,200)
        saved=self.app['engine'].profile_path.read_text();p['poses'][2]=p['poses'][1]
        r=await self.client.post('/api/save',json=p,headers=self.headers);self.assertEqual(r.status,400);self.assertEqual(self.app['engine'].profile_path.read_text(),saved)
    async def test_cross_origin_denied(self):
        h={**self.headers,'Origin':'https://example.com'};r=await self.client.post('/api/connect',json={},headers=h);self.assertEqual(r.status,403)
    async def test_dangerous_query_not_executable(self):
        r=await self.client.post('/api/read',json={'feature':'factory_restore'},headers=self.headers);self.assertEqual(r.status,400)
    async def test_mouse_requires_saved_calibration(self):
        r=await self.client.post('/api/options',json={'mouse':True},headers=self.headers);self.assertEqual(r.status,400);self.assertFalse(self.app['engine'].options['mouse'])

if __name__=='__main__':unittest.main()
