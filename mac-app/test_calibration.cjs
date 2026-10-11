const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const Flow=require('./web/calibration-flow.js');
const Motion=require('./web/ring-motion.js');
const z=Math.sqrt(.75),directions=[[0,0,1],[-.5,0,z],[.5,0,z],[0,-.5,z],[0,.5,z]];
const stable=(pose,start=0)=>Array.from({length:17},(_,i)=>({time:start+i*200,v:pose}));

test('stable posture needs enough fresh continuous samples',()=>{
 assert.equal(Flow.evaluatePose(stable(directions[0]).slice(0,5),800,0,[]).ready,false);
 assert.equal(Flow.evaluatePose(stable(directions[0]),3200,0,[]).ready,true);
 assert.equal(Flow.evaluatePose(stable(directions[0]),4000,0,[]).ready,false);
 const full=stable(directions[0]),gap=full.slice(0,5).concat(full.slice(12));
 assert.equal(Flow.evaluatePose(gap,3200,0,[]).ready,false);
});
test('moving posture cannot be confirmed',()=>{
 const moving=stable(directions[0]).map((s,i)=>({...s,v:directions[i%2]}));
 assert.equal(Flow.evaluatePose(moving,3200,0,[]).ready,false);
});
test('calibration tolerates lower update rate and short BLE delay',()=>{
 const slower=Array.from({length:7},(_,i)=>({time:i*500,v:directions[0]}));
 assert.equal(Flow.evaluatePose(slower,3100,0,[]).ready,true);
 assert.equal(Flow.evaluatePose(slower,3800,0,[]).ready,false);
});
test('ready posture remains confirmable between packets at uneven frame intervals',()=>{
 const slower=Array.from({length:10},(_,i)=>({time:i*370,v:directions[0]}));
 assert.equal(Flow.evaluatePose(slower,3330,0,[]).ready,true);
 assert.equal(Flow.evaluatePose(slower,3730,0,[]).ready,true);
});
test('each direction must differ correctly from previous poses',()=>{
 for(let i=0;i<5;i++)assert.equal(Flow.evaluatePose(stable(directions[i]),3200,i,directions.slice(0,i)).ready,true);
 for(let i=1;i<5;i++)assert.equal(Flow.evaluatePose(stable(directions[i-1]),3200,i,directions.slice(0,i)).ready,false);
});
test('confirmation rejects inactive, replayed, delayed and burst events',()=>{
 const wall=Date.now(),event={code:3,calibration:true,gesture:{sequence:2,time:new Date(wall).toISOString()}};
 const c={connected:true,visible:true,busy:false,lastSequence:1,lastConfirmation:0,now:2000,wallNow:wall};
 assert.equal(Flow.canConfirmGesture(event,c),true);
 for(const changed of [{connected:false},{visible:false},{busy:true},{lastSequence:2},{lastConfirmation:1500},{wallNow:wall+3000}])assert.equal(Flow.canConfirmGesture(event,{...c,...changed}),false);
 assert.equal(Flow.canConfirmGesture({...event,calibration:false},c),false);
});

function page(){
 let now=0;const nodes={},events={},posts=[],navigation=[];
 const html=fs.readFileSync(__dirname+'/web/calibration.html','utf8');
 for(const id of [...html.matchAll(/id="([^"]+)"/g)].map(x=>x[1]))nodes[id]={textContent:'',style:{},disabled:false,value:'220',classList:{toggle(){},remove(){}}};
 nodes.pad.clientWidth=600;nodes.pad.clientHeight=420;
 const steps=Array.from({length:5},()=>({className:'',querySelector(){return {textContent:''}}}));
 const section={hidden:false},parent={document:{getElementById(){return section}},async switchTab(name){navigation.push(name);section.hidden=true}};
 const window={parent,addEventListener(name,fn){events[name]=fn}};
 const context=vm.createContext({window,document:{visibilityState:'visible',getElementById(id){assert.ok(nodes[id],id);return nodes[id]},querySelectorAll(){return steps}},
  location:{hostname:'127.0.0.1',host:'127.0.0.1:18769',origin:'http://127.0.0.1:18769'},
  performance:{now:()=>now},CalibrationFlow:Flow,RingMotion:Motion,Date,console,Math,setInterval(){},setTimeout(){},requestAnimationFrame(){},
  WebSocket:class{},fetch:async(url,options)=>{if(url==='/api/save')posts.push(JSON.parse(options.body));return {ok:true,json:async()=>url==='/api/profile'?{profile:null}:{ok:true}}}});
 vm.runInContext(fs.readFileSync(__dirname+'/web/calibration.js','utf8'),context);
 const send=data=>vm.runInContext('socket',context).onmessage({data:JSON.stringify(data)});
 send({type:'status',connected:true});
 let sequence=0;
 const tap=()=>send({type:'gesture',code:3,calibration:true,gesture:{sequence:++sequence,time:new Date().toISOString()}});
 const hold=pose=>{for(let i=0;i<18;i++){now+=200;send({type:'accel',raw:pose.map(x=>Math.round(x*8192))})}};
 return {context,nodes,section,posts,navigation,events,parent,send,tap,hold,advance(ms){now+=ms},read:expr=>vm.runInContext(expr,context)};
}
test('all five poses and final save work using ring taps only',async()=>{
 const p=page();p.tap();assert.equal(p.read('poses.length'),0);
 for(let i=0;i<5;i++){
  p.hold(directions[i]);assert.equal(p.read('readiness.ready'),true);
  p.tap();assert.equal(p.read('poses.length'),i+1);
  p.tap();assert.equal(p.read('poses.length'),i+1);assert.equal(p.posts.length,0);
 }
 p.advance(1200);p.tap();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(p.posts.length,1);assert.equal(p.posts[0].poses.length,5);assert.deepEqual(p.navigation,['dashboard']);
 p.advance(2000);p.tap();await new Promise(resolve=>setImmediate(resolve));assert.equal(p.posts.length,1);
});
test('hidden calibration cannot consume ring taps; reenter resets unfinished poses',()=>{
 const p=page();p.hold(directions[0]);p.section.hidden=true;p.tap();assert.equal(p.read('poses.length'),0);
 p.section.hidden=false;p.hold(directions[0]);p.tap();assert.equal(p.read('poses.length'),1);
 p.events.message({origin:'http://127.0.0.1:18769',source:p.parent,data:{type:'qring-calibration-enter'}});
 assert.equal(p.read('poses.length'),0);assert.equal(p.posts.length,0);
});
test('disconnect discards unfinished poses without saving',()=>{
 const p=page();p.hold(directions[0]);p.tap();assert.equal(p.read('poses.length'),1);
 p.send({type:'status',connected:false,message:'disconnected'});
 assert.equal(p.read('poses.length'),0);assert.equal(p.posts.length,0);
 p.tap();assert.equal(p.read('poses.length'),0);
});
test('selected calibration works without window focus but hidden tab still rejects taps',()=>{
 const p=page();p.context.document.visibilityState='hidden';
 p.hold(directions[0]);p.tap();assert.equal(p.read('poses.length'),1);
 p.section.hidden=true;p.hold(directions[1]);p.tap();assert.equal(p.read('poses.length'),1);
});


test('direction preview accepts configurable angular neighborhoods and neutral wins',()=>{
 const axes=[[0,0,1],[-1,0,0],[0,-1,0]],rad=x=>x*Math.PI/180;
 const raw=degrees=>[-Math.sin(rad(degrees))*8192,0,Math.cos(rad(degrees))*8192];
 assert.equal(Motion.target(raw(45),directions,axes,220,{direction_range_right:20}).direction,'right');
 assert.equal(Motion.target(raw(45),directions,axes,220,{direction_range_right:10}).direction,'free');
 const wide={direction_range_right:60,direction_range_left:60,direction_range_up:60,direction_range_down:60};
 assert.equal(Motion.target(raw(35),directions,axes,220,wide).direction,'right');
 assert.deepEqual(Motion.target(raw(4),directions,axes,220,wide).velocity,[0,0]);
 assert.equal(Motion.target(raw(12),directions,axes,220,{neutral_zone:15}).direction,'neutral');
 assert.deepEqual(Motion.target([0,0,0],directions,axes,220).velocity,[0,0]);
 assert.equal(Motion.target(raw(80),directions,axes,220,{direction_range_right:20}).direction,'outside');
 assert.equal(Motion.target(raw(80),directions,axes,220,{direction_range_right:55}).direction,'right');
});
test('calibration preview keeps moving through gaps but respects pause, disconnect and hidden tab',()=>{
 const p=page();for(let i=0;i<5;i++){p.hold(directions[i]);p.tap();}
 p.hold(directions[1]);const before=Array.from(p.read('position'));p.advance(1000);p.read('animate()');
 assert.ok(p.read('position[0]')>before[0]);
 p.read('paused=true');const paused=Array.from(p.read('position'));p.advance(1000);p.read('animate()');assert.deepEqual(Array.from(p.read('position')),paused);
 p.read('paused=false');p.section.hidden=true;p.advance(1000);p.read('animate()');assert.deepEqual(Array.from(p.read('position')),paused);
});
