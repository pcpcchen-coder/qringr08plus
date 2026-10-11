const $=id=>document.getElementById(id);
const unit=v=>{const n=Math.hypot(...v);if(n<.01)throw Error('資料無效');return v.map(x=>x/n)};
const dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0);
let socket,connected=false,samples=[],poses=[],step=0,capturing=false,saving=false,profile=null,last=0;
let paused=false,position=[.5,.5],velocity=[0,0],saveDirty=true,readiness=null,lastConfirmation=-Infinity,lastGestureSequence=0,feedbackUntil=0;
const local=['127.0.0.1','localhost'].includes(location.hostname);
let motionSettings={};
function refreshMotionSettings(){if(local)fetch('/api/state').then(r=>r.json()).then(s=>motionSettings=s.options||{}).catch(()=>{});}
refreshMotionSettings();
function calibrationVisible(){try{const section=window.parent.document.getElementById('calibration');return !section||!section.hidden;}catch{return false;}}
function dual(p){
 if(p.length!==5)throw Error('請完成中立與四個方向校正。');
 const n=unit(p[0]),project=v=>{const g=unit(v),d=dot(g,n);if(d>Math.cos(8*Math.PI/180)||d<.5)throw Error('請保持約 10–60 度的傾斜姿勢。');return unit(g.map((x,i)=>x-d*n[i]))};
 const rr=project(p[1]),ll=project(p[2]),uu=project(p[3]),dd=project(p[4]);
 if(dot(rr,ll)>-.2||dot(uu,dd)>-.2)throw Error('相反方向太接近，請重新校正右／左與上／下。');
 const r=unit(rr.map((x,i)=>x-ll[i])),u=unit(uu.map((x,i)=>x-dd[i])),c=dot(r,u),den=1-c*c;
 if(den<.2)throw Error('水平與垂直方向太接近，請重新校正。');
 return [n,r.map((x,i)=>(x-c*u[i])/den),u.map((x,i)=>(x-c*r[i])/den)];
}
function message(s,hold=0){
 $('message').textContent=s;if(hold)feedbackUntil=performance.now()+hold;
 if(window.parent!==window&&calibrationVisible()){
  const note=window.parent.document.querySelector?.('.cal-note');
  if(note){note.textContent=(step<5?'第 '+(step+1)+'/5 步：'+['中立','向右','向左','向上','向下'][step]+' — ':'方向測試 — ')+s;note.dataset.ready=String(!!readiness?.ready);}
 }
}
function update(){
 document.querySelectorAll('#steps li').forEach((li,i)=>{li.className=i<poses.length?'done':i===step?'active':'';li.querySelector('b').textContent=i<poses.length?'已確認':i===step&&connected?(readiness?.ready?'單擊確認':'保持姿勢'):'待校正';});
 $('capture').disabled=!connected||!calibrationVisible()||capturing||saving||step>=5||!readiness?.ready;
 $('capture').textContent=step<5?(readiness?.ready?'確認'+['中立','向右','向左','向上','向下'][step]+'姿勢（也可單擊戒指）':'自動採樣中，保持姿勢…'):'五步方向已完成';
 $('save').disabled=!profile||!connected||capturing||saving||!saveDirty;
 $('save').textContent=saving?'儲存中…':saveDirty?'儲存校正（也可單擊戒指）':'已儲存';
 $('connect').disabled=connected||capturing||saving;$('disconnect').disabled=!connected;
 $('status').className='badge'+(connected?' connected':'');$('status').textContent=connected?'R08 已連線':'尚未連線';
}
function setStep(){
 const titles=['保持舒服的中立姿勢','傾斜到「向右」的姿勢','傾斜到「向左」的姿勢','傾斜到「向上」的姿勢','傾斜到「向下」的姿勢','試試四個方向，再單擊儲存'];
 const texts=['保持你想讓游標停止的姿勢約 3 秒。提示就緒後，單擊戒指確認。','從中立傾斜到想向右的姿勢，靜止約 3 秒，再單擊戒指。','回到中立，再傾斜到向左的姿勢。靜止約 3 秒，再單擊戒指。','回到中立，再傾斜到向上的姿勢。靜止約 3 秒，再單擊戒指。','回到中立，再傾斜到向下的姿勢。靜止約 3 秒，再單擊戒指。','確認四個方向與中立停止都符合直覺。單擊戒指儲存並返回裝置與量測。'];
 $('title').textContent=titles[step];$('instruction').textContent=texts[step];update();
}
function refreshReadiness(){
 if(!connected||!calibrationVisible()||capturing||saving||step>=5)return;
 readiness=CalibrationFlow.evaluatePose(samples,performance.now(),step,poses);
 $('progress').style.width=(readiness.progress*100)+'%';$('capture').classList.toggle('ready',readiness.ready);
 if(performance.now()>=feedbackUntil)message(readiness.reason+'（已收到 '+samples.length+' 筆）');update();
}
async function api(path,data={}){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await r.json();if(!r.ok)throw Error(result.error||'操作失敗');return result;}
async function connect(){if(!local)return;try{$('connect').disabled=true;$('status').textContent='連接中…';await api('/api/connect');message('正在尋找戒指，請保持手機 QRing 斷線。');}catch(e){message(e.message);update();}}
function handleRingGesture(d){
 const now=performance.now();
 const allowed=CalibrationFlow.canConfirmGesture(d,{connected,visible:calibrationVisible(),busy:capturing||saving,lastSequence:lastGestureSequence,lastConfirmation,now,wallNow:Date.now()});
 if(d.gesture?.sequence>lastGestureSequence)lastGestureSequence=d.gesture.sequence;
 if(d.code===3&&allowed){if(step<5)capture();else if(profile&&saveDirty){lastConfirmation=now;save();}}
 if(d.code===4&&d.calibration===true&&profile&&calibrationVisible()){paused=!paused;message(paused?'測試已暫停，長按可繼續。':'測試已恢復。',1500);}
}
function openSocket(){
 socket=new WebSocket(`ws://${location.host}/ws`);
 socket.onmessage=event=>{
  const d=JSON.parse(event.data);
  if(d.type==='status'){const wasConnected=connected;connected=d.connected;if(connected){if(!wasConnected){samples=[];readiness=null;setStep();message('自動採樣已開始，姿勢穩定後單擊戒指確認。');}}else{velocity=[0,0];samples=[];readiness=null;if(wasConnected)reset();update();if(d.message)message(d.message+(wasConnected?'；重新連線後從中立姿勢開始。':''));}}
  if(d.type==='accel'){
   const now=performance.now();last=now;const norm=Math.hypot(...d.raw)/8192;
   if(calibrationVisible()){if(norm>=.8&&norm<=1.2)samples.push({time:now,v:unit(d.raw)});else samples=[];samples=samples.filter(s=>now-s.time<6000);}
   $('xyz').textContent=d.raw.map(x=>(x/8192).toFixed(2)).join(' / ');$('fresh').textContent=norm>=.8&&norm<=1.2?'資料正常':'請減慢動作';
   const recent=samples.filter(s=>now-s.time<2000);$('hz').textContent=recent.length>2?`${((recent.length-1)*1000/(recent.at(-1).time-recent[0].time)).toFixed(1)} 筆／秒`:'量測中';
   if(profile){const result=RingMotion.target(d.raw,profile.poses,dual(profile.poses),Number($('speed').value),motionSettings);velocity=['neutral','invalid','outside'].includes(result.direction)?[0,0]:velocity.map((x,i)=>x*.4+result.velocity[i]*.6);}else velocity=[0,0];
   refreshReadiness();
  }
  if(d.type==='gesture')handleRingGesture(d);
 };
 socket.onclose=()=>{connected=false;velocity=[0,0];samples=[];readiness=null;lastGestureSequence=0;reset();update();message('本機服務已中斷，重新連線後從中立姿勢開始；原先儲存的校正不變。');setTimeout(openSocket,2500);};
}
function capture(){
 if(!connected||!calibrationVisible()||capturing||saving||step>=5)return false;
 readiness=CalibrationFlow.evaluatePose(samples,performance.now(),step,poses);
 if(!readiness.ready){message('單擊已收到：'+readiness.reason,1500);update();return false;}
 try{
  const candidate=[...poses,readiness.pose];if(candidate.length===5)dual(candidate);
  poses=candidate;step=poses.length;lastConfirmation=performance.now();samples=[];readiness=null;
  $('progress').style.width='0';$('capture').classList.remove('ready');
  if(step===5){profile={version:2,name:'R08_E703',poses,speed:Number($('speed').value)};saveDirty=true;$('padHint').textContent='傾斜測試方向 · 單擊儲存 · 長按暫停';position=[.5,.5];velocity=[0,0];message('五步已確認。試好方向後，單擊戒指儲存並返回裝置與量測。',1500);}else message('已確認。請做出下一個姿勢，穩定後再單擊戒指。',1000);
  setStep();return true;
 }catch(e){message(e.message,1500);return false;}
}
function reset(){if(capturing||saving)return;poses=[];step=0;profile=null;readiness=null;samples=[];velocity=[0,0];position=[.5,.5];paused=false;saveDirty=true;feedbackUntil=0;$('progress').style.width='0';$('capture').classList.remove('ready');$('padHint').textContent='完成四個方向後，即可測試移動';message('校正已重置，已儲存的設定不會被刪除。');setStep();}
async function save(){
 if(!connected||!profile||!saveDirty||saving||!calibrationVisible())return;
 saving=true;update();
 try{profile.speed=Number($('speed').value);await api('/api/save',profile);saveDirty=false;message('已儲存到這台 Mac。返回裝置與量測後可啟用戒指滑鼠。',1500);if(window.parent!==window&&typeof window.parent.switchTab==='function')await window.parent.switchTab('dashboard');}
 catch(e){message(e.message,2000);}finally{saving=false;update();}
}
$('connect').onclick=connect;$('capture').onclick=capture;$('reset').onclick=reset;$('save').onclick=save;
$('center').onclick=()=>{position=[.5,.5];velocity=[0,0];};$('speed').oninput=()=>{$('speedValue').textContent=$('speed').value;saveDirty=true;update();};
$('disconnect').onclick=async()=>{try{const result=await api('/api/disconnect');message(result.message);}catch(e){message(e.message);}};
window.addEventListener('message',event=>{if(event.origin===location.origin&&event.source===window.parent&&event.data?.type==='qring-calibration-enter'){refreshMotionSettings();reset();}});
setInterval(refreshReadiness,100);
let frame=performance.now();
function animate(frameTime){const now=performance.now();const dt=Math.min(.04,(now-frame)/1000);frame=now;const pad=$('pad');if(profile&&connected&&!paused&&calibrationVisible()){position[0]=Math.max(.025,Math.min(.975,position[0]+velocity[0]*dt/pad.clientWidth));position[1]=Math.max(.035,Math.min(.965,position[1]+velocity[1]*dt/pad.clientHeight));}$('cursor').style.left=position[0]*100+'%';$('cursor').style.top=position[1]*100+'%';if(connected&&now-last>600)$('fresh').textContent=velocity.some(x=>x!==0)?'延續移動，等待新資料':'等待新資料';requestAnimationFrame(animate);}
requestAnimationFrame(animate);
if(local){if(window.parent===window)api('/api/options',{calibration:true}).catch(e=>message(e.message));openSocket();fetch('/api/profile').then(r=>r.json()).then(d=>{if(d.profile)message('這台 Mac 已有儲存的設定；完成新校正並確認儲存後才會取代。',1500);}).catch(()=>message('本機服務尚未啟動。'));}
else{$('connect').hidden=true;$('localLink').hidden=false;$('hostedNote').hidden=false;$('title').textContent='在你的 Mac 上完成校正';$('instruction').textContent='請開啟本機版本，保持姿勢後以戒指單擊確認中立、右、左、上、下。';$('reset').disabled=true;$('speed').disabled=true;message('請先啟動 Mac 上的校正工具。');}
if(document.modelContext?.registerTool)document.modelContext.registerTool({name:'get_calibration_status',description:'Read ring connection and calibration progress.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true},execute:input=>{if(input&&Object.keys(input).length)throw Error('No parameters allowed');return {connected,recordedPoses:poses.length,readyToConfirm:!!readiness?.ready,readyToSave:!!profile,paused,saved:!saveDirty};}});
