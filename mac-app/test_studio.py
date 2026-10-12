"""Synthetic unit/API tests. No physical health data or mouse events."""
import asyncio
import json
import math
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from aiohttp.test_utils import TestClient,TestServer
from device import Device,SnapshotStats,pack,NOTIFY,Q
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
    async def test_poll_period_and_pause_have_distinct_timing(self):
        d=self.device;d.options.update(accel=True,accel_period=.02,accel_timeout=.03,accel_interval=.005)
        sent=[]
        async def send(op,payload=b'',**kw):
            if op==0xa1 and payload==b'\x03':
                sent.append(time.monotonic())
                d.notify(SimpleNamespace(uuid=NOTIFY),pack(0xa1,b'\x03\x00\x00\x00\x00\x20\x00'))
                if len(sent)==5:d.stop.set()
        d.send=send;await d.polling()
        self.assertEqual(len(sent),5)
        self.assertTrue(all(b-a>=.019 for a,b in zip(sent,sent[1:])))
        self.assertEqual(d.poll_stats.sent,5);self.assertEqual(d.poll_stats.received,5)
        self.assertEqual(d.poll_stats.waited,5);self.assertEqual(d.poll_stats.timeouts,0)
    async def test_poll_timeout_then_pause_when_ring_does_not_respond(self):
        d=self.device;d.options.update(accel=True,accel_period=0,accel_timeout=.005,accel_interval=.006)
        sent=[]
        async def send(op,payload=b'',**kw):
            sent.append(time.monotonic())
            if len(sent)==3:d.stop.set()
        d.send=send;await d.polling()
        self.assertTrue(all(b-a>=.010 for a,b in zip(sent,sent[1:])))
        self.assertEqual(d.poll_stats.timeouts,3);self.assertEqual(d.poll_stats.received,0)
    async def test_fastest_poll_stays_sequential_and_yields_without_fake_timeouts(self):
        d=self.device;d.options.update(accel=True,accel_period=0,accel_timeout=0,accel_interval=0)
        writes=0;concurrent=0;maximum=0;beats=0
        async def send(*args,**kw):
            nonlocal writes,concurrent,maximum
            concurrent+=1;maximum=max(maximum,concurrent);await asyncio.sleep(0)
            concurrent-=1;writes+=1
            if writes==6:d.stop.set()
        async def heartbeat():
            nonlocal beats
            while not d.stop.is_set():beats+=1;await asyncio.sleep(0)
        d.send=send;await asyncio.gather(d.polling(),heartbeat())
        self.assertEqual(writes,6);self.assertEqual(maximum,1);self.assertGreater(beats,1)
        self.assertEqual(d.poll_stats.no_wait,6);self.assertEqual(d.poll_stats.waited,0)
        self.assertEqual(d.poll_stats.timeouts,0)
    async def test_poll_stats_distinguish_arrivals_changes_timeouts_and_stale_data(self):
        stats=SnapshotStats(now=0)
        for t in (.2,1.3,2.7):stats.record_send(t)
        for t,v in ((.1,[1,2,3]),(.5,[1,2,3]),(1.5,[2,2,3]),(2.5,[2,2,3])):stats.record_sample(v,t)
        stats.record_wait(.01,False);stats.record_wait(.03,True)
        s=stats.snapshot(3)
        self.assertEqual((s['tx_hz'],s['rx_hz'],s['change_hz']),(1,1,.5))
        self.assertEqual((s['sent'],s['received'],s['changed']),(3,4,1))
        self.assertAlmostEqual(s['mean_wait_ms'],20);self.assertEqual(s['timeout_percent'],50)
        self.assertEqual(s['sample_age'],.5);self.assertEqual(s['max_gap_ms'],1000)
        self.assertEqual(stats.snapshot(6)['rx_hz'],0)
        self.assertIsNone(SnapshotStats(now=0).snapshot(1)['sample_age'])
    async def test_poll_preferences_persist_and_do_not_change_mouse_or_manual_measurement(self):
        d=self.device;z=math.sqrt(.75)
        d.profile_path.write_text(json.dumps({'version':2,'name':'R08_E703','speed':220,'poses':[[0,0,1],[-.5,0,z],[.5,0,z],[0,-.5,z],[0,.5,z]]}))
        await d.set_options({'gesture_debounce':.2,'direction_range_right':30})
        d.options['mouse']=True;d.control.paused=False;d.control.velocity=(77,0);d.active=2
        with patch.object(Q,'CGPreflightPostEventAccess',return_value=True):
            await d.set_options({'accel_period':.01,'accel_timeout':0,'accel_interval':0})
        self.assertFalse(d.control.paused);self.assertEqual(d.control.velocity,(77,0))
        self.assertFalse(d.measure_done.is_set())
        restored=Device(self.temp.name)
        try:
            self.assertEqual(restored.options['accel_period'],.01)
            self.assertEqual(restored.options['accel_timeout'],0);self.assertEqual(restored.options['accel_interval'],0)
            self.assertEqual(restored.options['gesture_debounce'],.2)
            self.assertEqual(restored.options['direction_range_right'],30)
            self.assertFalse(restored.options['mouse']);self.assertTrue(restored.control.paused)
        finally:restored.log_file.close()
    async def test_stat_reset_during_inflight_wait_does_not_add_old_wait_to_new_run(self):
        d=self.device;old=d.poll_stats;old.record_send(time.monotonic())
        d.reset_poll_stats();old.record_wait(.1,True)
        self.assertEqual(d.poll_stats.snapshot(time.monotonic())['timeouts'],0)
        self.assertEqual(d.poll_stats.sent,0)
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
    async def test_menu_status_matches_control_guards(self):
        d=self.device
        with patch.object(Q,'CGPreflightPostEventAccess',return_value=True):
            self.assertEqual(d.control_snapshot()['mode'],'disconnected')
            d.state['connected']=True
            self.assertEqual(d.control_snapshot()['mode'],'off')
            d.options['mouse']=True
            self.assertEqual(d.control_snapshot()['mode'],'paused')
            d.active=1
            self.assertEqual(d.control_snapshot()['mode'],'measuring')
            d.active=None;d.control.paused=False;d.control.last=time.monotonic()-1
            self.assertEqual(d.control_snapshot()['mode'],'stale')
            d.control.last=time.monotonic();d.control.velocity=(0,0)
            self.assertEqual(d.control_snapshot()['mode'],'ready')
            d.control.velocity=(120,0)
            self.assertEqual(d.control_snapshot()['mode'],'moving')
            d.control.last=time.monotonic()-3
            self.assertEqual(d.control_snapshot()['mode'],'holding')
            with patch.object(Q,'CGPreflightPostEventAccess',return_value=False):
                self.assertEqual(d.control_snapshot()['mode'],'permission')
    async def test_resume_rejects_unsafe_states_and_resets_velocity(self):
        d=self.device
        with self.assertRaises(ValueError):d.resume_mouse()
        d.state['connected']=True
        with self.assertRaises(ValueError):d.resume_mouse()
        d.options['mouse']=True
        with patch.object(Q,'CGPreflightPostEventAccess',return_value=False):
            with self.assertRaises(ValueError):d.resume_mouse()
        with patch.object(Q,'CGPreflightPostEventAccess',return_value=True):
            d.active=1
            with self.assertRaises(ValueError):d.resume_mouse()
            d.active=None;d.control.velocity=(120,120)
            d.resume_mouse()
            self.assertFalse(d.control.paused);self.assertEqual(d.control.velocity,(0,0))
    async def test_repeated_long_press_has_distinct_feedback_and_actions(self):
        d=self.device;d.options['mouse']=True
        char=SimpleNamespace(uuid=NOTIFY);frame=pack(0x73,bytes([0x2d,4]))
        with patch('device.time.monotonic',return_value=100):d.notify(char,frame)
        first=d.state['values']['gesture'].copy()
        with patch('device.time.monotonic',return_value=101):d.notify(char,frame)
        second=d.state['values']['gesture']
        self.assertEqual(first['name'],second['name']);self.assertEqual(second['sequence'],2);self.assertEqual(second['count'],2)
        self.assertEqual(first['action'],'游標控制已開始');self.assertEqual(second['action'],'游標已暫停')
        self.assertEqual([g['sequence'] for g in d.snapshot()['gesture_history']],[2,1])
    async def test_configurable_interval_gates_actions_but_keeps_events(self):
        d=self.device;d.options.update(mouse=True,gesture_debounce=1)
        char=SimpleNamespace(uuid=NOTIFY);frame=pack(0x73,bytes([0x2d,4]))
        for stamp in (100,100.3):
            with patch('device.time.monotonic',return_value=stamp):d.notify(char,frame)
        self.assertFalse(d.control.paused);self.assertEqual(d.gesture_sequence,2)
        self.assertEqual(d.state['values']['gesture']['action'],'已收到；未重複執行控制')
        with patch('device.time.monotonic',return_value=101):d.notify(char,frame)
        self.assertTrue(d.control.paused)
        d.options['gesture_debounce']=0
        for _ in range(2):
            with patch('device.time.monotonic',return_value=101):d.notify(char,frame)
        self.assertTrue(d.control.paused);self.assertEqual(d.gesture_sequence,5)
        self.assertEqual(d.state['values']['gesture']['action'],'游標已暫停')
    async def test_interval_persists_without_restoring_mouse_or_health(self):
        d=self.device;await d.set_options({'gesture_debounce':.13})
        self.assertEqual(json.loads(d.preferences_path.read_text()),{'gesture_debounce':.13})
        restored=Device(self.temp.name)
        try:
            self.assertEqual(restored.options['gesture_debounce'],.13)
            self.assertFalse(any(restored.options[k] for k in ('mouse','click','hr','spo2','touch')))
            restored.active=2;restored.measure_done.clear()
            await restored.set_options({'gesture_debounce':.2})
            self.assertFalse(restored.measure_done.is_set())
        finally:restored.log_file.close()
    async def test_motion_ranges_persist_and_keep_existing_preferences(self):
        d=self.device;await d.set_options({'gesture_debounce':.2})
        await d.set_options({'direction_range_right':35,'direction_range_left':18,'neutral_zone':12})
        saved=json.loads(d.preferences_path.read_text())
        self.assertEqual(saved['gesture_debounce'],.2);self.assertEqual(saved['direction_range_right'],35)
        await d.set_options({'gesture_debounce':.1})
        self.assertEqual(json.loads(d.preferences_path.read_text())['direction_range_right'],35)
        restored=Device(self.temp.name)
        try:
            self.assertEqual(restored.control.direction_ranges['right'],35)
            self.assertEqual(restored.control.neutral_zone,12)
            self.assertTrue(restored.control.hold_between_samples)
            self.assertFalse(restored.options['mouse']);self.assertTrue(restored.control.paused)
        finally:restored.log_file.close()
    async def test_continuous_movement_neutral_and_explicit_pause(self):
        d=self.device;c=d.control;z=math.sqrt(.75)
        c.load_profile({'version':2,'speed':220,'poses':[[0,0,1],[-.5,0,z],[.5,0,z],[0,-.5,z],[0,.5,z]]})
        c.paused=False;c.update((-4096,0,7094),1)
        velocity=c.current(1);self.assertGreater(velocity[0],0)
        self.assertEqual(c.current(1.36),velocity);self.assertEqual(c.current(20),velocity)
        c.update((0,0,8192),21);self.assertEqual(c.current(21),(0,0))
        self.assertEqual(c.direction,'neutral');self.assertEqual(c.current(50),(0,0))
        c.update((-4096,0,7094),51);c.paused=True;self.assertEqual(c.current(60),(0,0))
    async def test_direction_ranges_have_real_boundaries_and_overlap_uses_nearest(self):
        c=self.device.control;z=math.sqrt(.75)
        c.load_profile({'version':2,'speed':220,'poses':[[0,0,1],[-.5,0,z],[.5,0,z],[0,-.5,z],[0,.5,z]]})
        raw=lambda angle:(-8192*math.sin(math.radians(angle)),0,8192*math.cos(math.radians(angle)))
        c.update(raw(45),1);self.assertEqual(c.direction,'right');self.assertAlmostEqual(c.deviations['right'],15)
        c.direction_ranges['right']=10;c.update(raw(45),2);self.assertEqual(c.direction,'free')
        c.direction_ranges={name:60 for name in ('right','left','up','down')}
        c.update(raw(35),3);self.assertEqual(c.direction,'right')
        c.update(raw(4),4);self.assertEqual(c.direction,'neutral');self.assertEqual(c.velocity,(0,0))
        c.neutral_zone=15;c.update(raw(12),5);self.assertEqual(c.direction,'neutral')
        c.update((0,0,0),6);self.assertEqual(c.direction,'invalid');self.assertEqual(c.velocity,(0,0))
    async def test_movement_does_not_post_while_disconnected_paused_or_measuring(self):
        d=self.device;d.options['mouse']=True;d.control.paused=False;d.control.velocity=(200,0)
        with patch.object(Q,'CGEventPost') as post,patch.object(Q,'CGPreflightPostEventAccess',return_value=True):
            for connected,paused,active in [(False,False,None),(True,True,None),(True,False,1)]:
                d.state['connected']=connected;d.control.paused=paused;d.active=active
                task=asyncio.create_task(d.movement());await asyncio.sleep(.04);d.stop.set();await task;d.stop.clear()
            post.assert_not_called()
    async def test_movement_posts_through_data_gap_with_held_velocity(self):
        d=self.device;d.state['connected']=True;d.options['mouse']=True
        d.control.paused=False;d.control.velocity=(100,0);d.control.last=time.monotonic()-4
        bounds=SimpleNamespace(origin=SimpleNamespace(x=0,y=0),size=SimpleNamespace(width=1000,height=1000))
        with patch.object(Q,'CGEventPost') as post,patch.object(Q,'CGPreflightPostEventAccess',return_value=True),\
             patch.object(Q,'CGEventCreate',return_value=None),\
             patch.object(Q,'CGEventGetLocation',return_value=SimpleNamespace(x=400,y=400)),\
             patch.object(Q,'CGDisplayBounds',return_value=bounds),patch.object(Q,'CGEventCreateMouseEvent',return_value=None):
            task=asyncio.create_task(d.movement());await asyncio.sleep(.06);d.stop.set();await task
            self.assertGreater(post.call_count,1)
    async def test_all_direction_ranges_work_with_rotated_ring_orientation(self):
        c=self.device.control;z=math.sqrt(.75)
        # Rotate the complete calibration to make neutral point along X, not Z.
        rotate=lambda v:[v[2],v[0],v[1]]
        poses=[rotate(v) for v in [[0,0,1],[-.5,0,z],[.5,0,z],[0,-.5,z],[0,.5,z]]]
        c.load_profile({'version':2,'speed':220,'poses':poses})
        for name,pose in zip(('right','left','up','down'),poses[1:]):
            c.update([x*8192 for x in pose],1)
            self.assertEqual(c.direction,name);self.assertAlmostEqual(c.deviations[name],0,places=5)
    async def test_expanded_direction_range_overrides_old_neutral_tilt_cutoff(self):
        c=self.device.control;z=math.sqrt(.75)
        c.load_profile({'version':2,'speed':220,'poses':[[0,0,1],[-.5,0,z],[.5,0,z],[0,-.5,z],[0,.5,z]]})
        raw=(-8192*math.sin(math.radians(80)),0,8192*math.cos(math.radians(80)))
        c.update(raw,1);self.assertEqual(c.direction,'outside');self.assertEqual(c.velocity,(0,0))
        c.direction_ranges['right']=55;c.update(raw,2)
        self.assertEqual(c.direction,'right');self.assertGreater(c.velocity[0],0)
    async def test_candidate_keeps_readings_and_completion_history(self):
        d=self.device;d.client=SimpleNamespace(is_connected=True)
        async def send(op,payload=b'',**kw):
            if op==0x69:
                d.notify(SimpleNamespace(uuid=NOTIFY),pack(0x69,bytes([2,0,87,12,34])))
                d.notify(SimpleNamespace(uuid=NOTIFY),pack(0x69,bytes([2,1,0])))
        d.send=send;await d.measure(2,manual=True)
        run=d.state['measurements']['bp']
        self.assertEqual(run['status'],'completed');self.assertEqual(run['response_count'],2)
        self.assertEqual(run['responses'][0]['value'],87);self.assertEqual(run['responses'][0]['raw_payload'][:5],[2,0,87,12,34])
        self.assertIn('69 02 00 57',run['responses'][0]['hex']);self.assertNotIn('mmHg',run['message']);self.assertIsNone(d.active)
    async def test_new_measurement_does_not_show_old_values_on_timeout(self):
        d=self.device;d.state['values']['bp']={'value':99,'time':'old'}
        async def send(*args,**kw):pass
        d.send=send;await d.measure(2,manual=True,timeout=0)
        run=d.state['measurements']['bp']
        self.assertEqual(run['status'],'timeout');self.assertIsNone(run['latest']);self.assertEqual(run['response_count'],0)
        self.assertEqual(run['responses'],[]);self.assertIsNotNone(run['ended_at'])
    async def test_candidate_failure_is_visible_and_unrelated_packet_cannot_finish_it(self):
        d=self.device;d.active=2
        d.notify(SimpleNamespace(uuid=NOTIFY),pack(0x69,bytes([1,0,75])))
        self.assertFalse(d.measure_done.is_set())
        async def send(*args,**kw):raise RuntimeError('synthetic disconnect')
        d.send=send
        with self.assertRaises(RuntimeError):await d.measure(2,manual=True)
        run=d.state['measurements']['bp'];self.assertEqual(run['status'],'failed');self.assertIn('synthetic disconnect',run['message']);self.assertIsNone(d.active)

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
    async def test_index_versions_assets_and_marks_page_non_cacheable(self):
        r=await self.client.get('/',headers=self.headers);self.assertEqual(r.status,200)
        html=await r.text();self.assertIn('studio.js?v=',html);self.assertIn('studio.css?v=',html)
        self.assertEqual(r.headers['Cache-Control'],'no-store');self.assertIn('touchHistory',html)
    async def test_calibration_page_versions_assets_and_disables_system_mouse(self):
        r=await self.client.get('/calibration.html',headers=self.headers)
        self.assertEqual(r.status,200);html=await r.text()
        self.assertIn('calibration-flow.js?v=',html);self.assertIn('calibration.js?v=',html)
        self.assertEqual(r.headers['Cache-Control'],'no-store')
        d=self.app['engine'];d.options.update(mouse=True,click=True)
        r=await self.client.post('/api/options',json={'calibration':True},headers=self.headers)
        self.assertEqual(r.status,200);self.assertFalse(d.options['mouse']);self.assertFalse(d.options['click'])
    async def test_interval_setting_api_rejects_invalid_values_without_overwriting(self):
        r=await self.client.post('/api/options',json={'gesture_debounce':.25},headers=self.headers)
        self.assertEqual(r.status,200);d=self.app['engine'];saved=d.preferences_path.read_text()
        for value in (-.1,2.1,True,'0.2',None):
            r=await self.client.post('/api/options',json={'gesture_debounce':value},headers=self.headers)
            self.assertEqual(r.status,400);self.assertEqual(d.options['gesture_debounce'],.25)
            self.assertEqual(d.preferences_path.read_text(),saved)
    async def test_polling_api_validates_bounds_and_reset_without_enabling_sensors(self):
        r=await self.client.post('/api/options',json={'accel_period':0,'accel_timeout':.001,'accel_interval':0},headers=self.headers)
        self.assertEqual(r.status,200);d=self.app['engine'];saved=d.preferences_path.read_text()
        for key in ('accel_period','accel_timeout','accel_interval'):
            for value in (-.001,2.001,True,'0.01',None,float('nan'),float('inf')):
                r=await self.client.post('/api/options',json={key:value},headers=self.headers)
                self.assertEqual(r.status,400);self.assertEqual(d.preferences_path.read_text(),saved)
        d.poll_stats.record_send(time.monotonic())
        h={**self.headers,'Origin':'https://example.com'}
        r=await self.client.post('/api/polling/reset',json={},headers=h);self.assertEqual(r.status,403)
        self.assertEqual(d.poll_stats.sent,1)
        r=await self.client.post('/api/polling/reset',json={},headers=self.headers);self.assertEqual(r.status,200)
        s=await (await self.client.get('/api/state',headers=self.headers)).json()
        self.assertEqual(s['polling']['sent'],0);self.assertFalse(s['polling']['active'])
        self.assertFalse(any(d.options[k] for k in ('accel','mouse','calibration','hr','spo2')))
    async def test_direction_settings_reject_invalid_values_and_keep_calibration(self):
        r=await self.client.post('/api/options',json={'direction_range_right':30,'neutral_zone':10},headers=self.headers)
        self.assertEqual(r.status,200);d=self.app['engine'];saved=d.preferences_path.read_text()
        for key,values in [('direction_range_right',(1,61,True,'30',None)),('neutral_zone',(-1,21,True,'10',None))]:
            for value in values:
                r=await self.client.post('/api/options',json={key:value},headers=self.headers)
                self.assertEqual(r.status,400);self.assertEqual(d.preferences_path.read_text(),saved)
        r=await self.client.get('/api/state',headers=self.headers);s=await r.json()
        self.assertEqual(s['options']['direction_range_right'],30)
        self.assertIn('deviations',s['control']);self.assertFalse(s['options']['mouse'])
    async def test_dangerous_query_not_executable(self):
        r=await self.client.post('/api/read',json={'feature':'factory_restore'},headers=self.headers);self.assertEqual(r.status,400)
    async def test_mouse_requires_saved_calibration(self):
        r=await self.client.post('/api/options',json={'mouse':True},headers=self.headers);self.assertEqual(r.status,400);self.assertFalse(self.app['engine'].options['mouse'])
    async def test_menu_status_is_small_and_resume_pause_are_shared(self):
        d=self.app['engine'];d.state['connected']=True;d.options['mouse']=True
        with patch.object(Q,'CGPreflightPostEventAccess',return_value=True):
            r=await self.client.get('/api/control-status',headers=self.headers)
            self.assertEqual(r.status,200);s=await r.json()
            self.assertEqual(s['mode'],'paused');self.assertNotIn('logs',s);self.assertNotIn('values',s)
            r=await self.client.post('/api/resume',json={},headers=self.headers)
            self.assertEqual(r.status,200);self.assertFalse(d.control.paused)
            r=await self.client.post('/api/pause',json={},headers=self.headers)
            self.assertEqual(r.status,200);self.assertTrue(d.control.paused)
            self.assertEqual(d.control.velocity,(0,0))
    async def test_resume_requires_permission_and_rejects_cross_origin(self):
        d=self.app['engine'];d.state['connected']=True;d.options['mouse']=True
        with patch.object(Q,'CGPreflightPostEventAccess',return_value=False):
            r=await self.client.post('/api/resume',json={},headers=self.headers)
            self.assertEqual(r.status,400);self.assertTrue(d.control.paused)
        h={**self.headers,'Origin':'https://example.com'}
        r=await self.client.post('/api/resume',json={},headers=h)
        self.assertEqual(r.status,403);self.assertTrue(d.control.paused)

if __name__=='__main__':unittest.main()
