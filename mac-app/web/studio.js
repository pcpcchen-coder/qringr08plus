const $=id=>document.getElementById(id);let state=null,tab='dashboard',busy=false;
const labels={mouse:'游標',click:'單擊',accel:'三軸加速度',touch:'觸控',hr:'心率',spo2:'血氧',battery:'電量',hr_auto:'內建心率排程',spo2_auto:'內建血氧排程',stress_auto:'內建壓力排程',hrv_auto:'內建 HRV 排程',stress:'壓力',glucose:'血糖',bp:'血壓',hrv:'HRV',temperature:'體溫',fatigue:'疲勞',composite:'綜合檢查',realtime_hr:'即時心率',capabilities:'能力位元'};
const text=(node,s)=>node.textContent=s,notice=s=>text($('notice'),s);
const timeLabel=value=>value?new Date(value).toLocaleTimeString('zh-TW',{hour12:false})+'.'+String(new Date(value).getMilliseconds()).padStart(3,'0'):'—';
let lastGestureSequence=0,gestureHistory=[],touchFlashTimer=null,announcedMeasurement=null;
let gestureIntervalDirty=false;
function editGestureInterval(value){gestureIntervalDirty=true;$('gestureDebounce').value=value;$('gestureDebounceRange').value=value}
async function saveGestureInterval(){
 const input=$('gestureDebounce'),value=Number(input.value);
 if(input.value===''||!Number.isFinite(value)||value<0||value>2){notice('請輸入 0–2 秒的觸控防重複間隔。');return}
 $('saveGestureInterval').disabled=true;
 try{await api('/api/options',{gesture_debounce:value});gestureIntervalDirty=false;await refresh();notice('已儲存觸控防重複間隔：'+value.toFixed(2)+' 秒，下次開啟會沿用。')}
 catch(e){notice(e.message)}finally{$('saveGestureInterval').disabled=false}
}
function renderGesture(gesture,history=[]){
 if(!gesture||gesture.sequence<lastGestureSequence)return;
 const isNew=gesture.sequence>lastGestureSequence;
 text($('touchValue'),`${gesture.name} · 第 ${gesture.count} 次`);
 text($('touchMeta'),`${timeLabel(gesture.time)} · 累計 ${gesture.sequence} 次 · ${gesture.action}`);
 if(isNew)lastGestureSequence=gesture.sequence;
 gestureHistory=[gesture,...history,...gestureHistory].filter((g,i,all)=>all.findIndex(x=>x.sequence===g.sequence)===i).sort((a,b)=>b.sequence-a.sequence).slice(0,6);
 const root=$('touchHistory');root.replaceChildren();
 for(const g of gestureHistory){const item=document.createElement('li');item.textContent=`${timeLabel(g.time)}　${g.name} #${g.count} · ${g.action}`;root.append(item)}
 if(!isNew)return;
 const row=$('touchEvent');row.classList.remove('touch-pulse');void row.offsetWidth;row.classList.add('touch-pulse');
 clearTimeout(touchFlashTimer);touchFlashTimer=setTimeout(()=>row.classList.remove('touch-pulse'),1400);
}
const candidateNames={2:'血壓',4:'疲勞',5:'綜合檢查',6:'即時心率',7:'心電圖',8:'壓力',9:'血糖',10:'HRV',11:'體溫'};
const candidateKeys={2:'bp',4:'fatigue',5:'composite',6:'realtime_hr',7:'ecg',8:'stress',9:'glucose',10:'hrv',11:'temperature'};
function renderCandidates(){
 if(!state)return;
 for(const [type]of Object.entries(candidateNames)){
  const run=state.measurements?.[candidateKeys[type]],row=$('candidate-'+type);
  if(!run){text($('candidateValue-'+type),type==='7'?'啟動流程未確認，尚未測試':'尚未測試');continue}
  const live=['waiting','running'].includes(run.status),r=run.latest;
  row.dataset.status=run.status;
  text($('candidateStatus-'+type),({waiting:'等待回應',running:'測試中',completed:'已結束',timeout:'逾時',cancelled:'已停止',failed:'未完成'})[run.status]);
  text($('candidateValue-'+type),r?`原始值：${r.value}（未解碼）`:'尚未收到本次讀值');
  text($('candidateMessage-'+type),run.message);
  const elapsed=Math.max(0,Math.floor(((live?Date.now():Date.parse(run.ended_at||run.updated_at))-Date.parse(run.started_at))/1000));
  text($('candidateMeta-'+type),`第 ${run.run_id} 次測試 · ${live?'已進行':'歷時'} ${elapsed} 秒${live?'／最長 '+run.timeout_seconds+' 秒':''} · 收到 ${run.response_count} 筆${r?' · 更新 '+timeLabel(r.time):''}`);
  text($('candidateRaw-'+type),r?`回應碼：${r.error} · 原始欄位：[${r.raw_payload.join(', ')}]`:'');
  const history=$('candidateHistory-'+type),signature=run.run_id+':'+run.response_count;
  if(history.dataset.signature!==signature){history.dataset.signature=signature;history.replaceChildren();const readings=$('candidateReadings-'+type);readings.replaceChildren();for(const [i,response]of [...run.responses].reverse().entries()){const li=document.createElement('li');li.textContent=`${timeLabel(response.time)} · ${response.hex}`;history.append(li);if(i<3){const value=document.createElement('li');value.textContent=`${timeLabel(response.time)} · 原始值 ${response.value} · 回應碼 ${response.error}`;readings.append(value)}}}
  $('candidateDetails-'+type).hidden=!run.response_count;
  const b=row.querySelector('[data-probe]');b.textContent=live?'測試中…':'再次單次測試';
 }
}
async function api(path,data={}){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const value=await r.json();if(!r.ok)throw Error(value.error||'操作失敗');return value}
async function action(fn){try{await fn();await refresh()}catch(e){notice(e.message)}}
async function switchTab(next){if(next===tab)return;await action(async()=>{await api('/api/options',{calibration:next==='calibration'});tab=next;document.querySelectorAll('.tab').forEach(el=>el.hidden=el.id!==tab);document.querySelectorAll('[data-tab]').forEach(el=>el.classList.toggle('selected',el.dataset.tab===tab));if(tab==='calibration'){if($('calFrame').src.endsWith('about:blank'))$('calFrame').src='/calibration.html?v=ring-confirm-v1';else $('calFrame').contentWindow.postMessage({type:'qring-calibration-enter'},location.origin)}render()})}
function render(){if(!state)return;const s=state;text($('connection'),s.connected?'已連線':s.message);$('connect').disabled=s.connected;$('disconnect').disabled=!s.connected;text($('name'),s.name);text($('hardware'),s.hardware||'硬體版本待讀取');text($('firmware'),s.firmware||'—');text($('serial'),s.serial?'序號：'+s.serial:'序號未提供');text($('battery'),s.battery===null?'—':`${s.battery}%`);text($('charging'),s.charging===null?'待讀取':s.charging?'充電中':'未充電');text($('autoStatus'),s.auto_status);text($('mouseStatus'),s.options.mouse?(s.paused?'已勾選，長按開始移動':(s.control?.label||'正在控制系統游標')):'尚未啟用');text($('calibrationStatus'),s.calibrated?'已有校正設定，啟用滑鼠會載入。':'請先完成中立、右、左、上、下校正。');
renderDirectionRanges(s);
if(!gestureIntervalDirty){const value=s.options.gesture_debounce??.5;$('gestureDebounce').value=value;$('gestureDebounceRange').value=value}text($('savedGestureInterval'),'目前套用：'+(s.options.gesture_debounce??.5).toFixed(2)+' 秒');
document.querySelectorAll('[data-option]').forEach(el=>{if(document.activeElement!==el)el.checked=!!s.options[el.dataset.option];el.disabled=!s.connected&&el.dataset.option!=='manage_auto'});$('healthInterval').value=String(s.options.health_interval);document.querySelectorAll('[data-read],[data-measure]').forEach(el=>el.disabled=!s.connected||s.active_measurement!==null);$('pause').disabled=!s.options.mouse;document.querySelectorAll('[data-probe]').forEach(el=>el.disabled=!s.connected||s.active_measurement!==null||el.dataset.probe==='7');$('readSelected').disabled=!s.connected;
text($('accelValue'),s.values.accel?s.values.accel.nominal_g.join(' / ')+' g':'—');renderGesture(s.values.gesture,s.gesture_history);text($('hrValue'),s.values.hr?(s.values.hr.display+' · '+s.values.hr.time.split('T')[1].slice(0,8)):'尚未量測');text($('spo2Value'),s.values.spo2?(s.values.spo2.display+' · '+s.values.spo2.time.split('T')[1].slice(0,8)):'尚未量測');renderCandidates();
if(s.active_measurement){announcedMeasurement=s.active_measurement;notice('量測中：'+({1:'心率',3:'血氧',...candidateNames}[s.active_measurement]||'候選項目')+'；游標暫停，最長 40 秒。')}else if(announcedMeasurement!==null){notice('單次測試已結束，請查看該項目的讀值與回應。');announcedMeasurement=null}
if(tab==='explore'){if(!$('readQuery').options.length){for(const q of s.read_queries){const option=document.createElement('option');option.value=q.key;option.textContent=(labels[q.key]||q.key)+' · 0x'+q.opcode;$('readQuery').append(option)}}const evidence=$('evidence');evidence.replaceChildren();for(const [key,value]of Object.entries(s.evidence)){const p=document.createElement('p');p.textContent=`${labels[key]||key}：${value}`;evidence.append(p)}text($('gatt'),JSON.stringify({capability_bytes:s.capabilities,channels:s.channels,gatt:s.gatt},null,2));catalog()}
if(tab==='messages')logs();}
function catalog(){if(!state)return;const query=$('catalogSearch').value.toLowerCase(),root=$('catalog');root.replaceChildren();for(const item of state.catalog){if(query&&!JSON.stringify(item).toLowerCase().includes(query))continue;const row=document.createElement('div');row.className='catalog-row';const h=document.createElement('h3');h.textContent=`${item.channel} · 0x${item.opcode} ${item.type?'／類型 '+item.type:''} · ${item.name}`;const small=document.createElement('small');small.textContent=`${item.category} · ${item.provenance} · ${item.reference}`;row.append(h,small);if(item.dangerous){const label=document.createElement('span');label.className='status-tag';label.textContent='破壞性功能：本版不提供執行';row.append(label)}root.append(row)}}
function logs(){if(!state)return;const direction=$('logFilter').value,query=$('logSearch').value.toLowerCase();const root=$('logs'),bottom=root.scrollTop+root.clientHeight>=root.scrollHeight-50;root.replaceChildren();for(const row of state.logs){if(direction&&row.direction!==direction)continue;if(query&&!JSON.stringify(row).toLowerCase().includes(query))continue;const el=document.createElement('div');el.className='entry';const b=document.createElement('b');b.textContent=row.direction;const span=document.createElement('span');span.textContent=row.time.split('T')[1].slice(0,12)+' · '+JSON.stringify(Object.fromEntries(Object.entries(row).filter(([k])=>!['time','direction'].includes(k))));el.append(b,span);root.append(el)}if(bottom)root.scrollTop=root.scrollHeight}
async function refresh(){if(busy)return;busy=true;try{const r=await fetch('/api/state');if(!r.ok)throw Error('無法取得 App 狀態');state=await r.json();render()}catch(e){notice('服務尚未就緒：'+e.message)}finally{busy=false}}
$('connect').onclick=()=>action(async()=>{await api('/api/connect');notice('正在連接，讀取資訊與內建排程可能需要十多秒。')});$('disconnect').onclick=()=>action(()=>api('/api/disconnect'));$('pause').onclick=()=>action(()=>api('/api/pause'));$('calibrationLink').onclick=()=>switchTab('calibration');document.querySelectorAll('[data-tab]').forEach(el=>el.onclick=()=>switchTab(el.dataset.tab));document.querySelectorAll('[data-option]').forEach(el=>el.onchange=()=>action(()=>api('/api/options',{[el.dataset.option]:el.checked})));$('healthInterval').onchange=()=>action(()=>api('/api/options',{health_interval:Number($('healthInterval').value)}));document.querySelectorAll('[data-read]').forEach(el=>el.onclick=()=>action(()=>api('/api/read',{feature:el.dataset.read})));document.querySelectorAll('[data-measure]').forEach(el=>el.onclick=()=>action(()=>api('/api/measure',{type:Number(el.dataset.measure)})));
for(const [type,name]of Object.entries(candidateNames)){
 const row=document.createElement('div');row.className='candidate-row';row.id='candidate-'+type;
 const head=document.createElement('div');head.className='candidate-head';
 const title=document.createElement('h3');title.textContent=name;
 const badge=document.createElement('span');badge.className='candidate-status';badge.id='candidateStatus-'+type;badge.textContent='尚未驗證';
 const b=document.createElement('button');b.textContent=type==='7'?'啟動流程未確認':'開始單次測試';b.disabled=type==='7';b.dataset.probe=type;
 b.onclick=()=>action(async()=>{b.disabled=true;await api('/api/measure',{type:Number(type)});notice(name+'單次測試已開始，結果會顯示在此項目下方。')});
 head.append(title,badge,b);row.append(head);
 for(const [part,tag,value]of [['Value','output',type==='7'?'啟動流程未確認，尚未測試':'尚未測試'],['Message','p','未知欄位保留原始值，不換算成健康數值。'],['Meta','small',''],['Raw','p','']]){const el=document.createElement(tag);el.id='candidate'+part+'-'+type;el.className='candidate-'+part.toLowerCase();el.textContent=value;row.append(el)}
 const details=document.createElement('details');details.id='candidateDetails-'+type;details.hidden=true;
 const readings=document.createElement('ul');readings.id='candidateReadings-'+type;readings.className='candidate-readings';row.append(readings);
 const summary=document.createElement('summary');summary.textContent='最近 6 筆原始回應';const history=document.createElement('ol');history.id='candidateHistory-'+type;
 details.append(summary,history);row.append(details);$('measureCandidates').append(row);
}
$('inventory').onclick=()=>action(async()=>{for(const feature of ['capabilities','notification_routes','hr_auto','spo2_auto','stress_auto','hrv_auto','bp_auto','temperature_auto','today_activity']){notice('讀取中：'+(labels[feature]||feature));await api('/api/read',{feature});await refresh()}notice('基本能力與排程已讀取，請查看實機證據與收發訊息。')});$('catalogSearch').oninput=catalog;$('logFilter').onchange=logs;$('logSearch').oninput=logs;$('export').onclick=()=>{if(window.webkit?.messageHandlers?.nativeExport){window.webkit.messageHandlers.nativeExport.postMessage({})}else{const a=document.createElement('a');a.href='/api/export';a.download='qring-session.jsonl';a.click()}};
refresh();setInterval(refresh,1000);
function connectGestureStream(){
 const socket=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
 socket.onmessage=event=>{try{const data=JSON.parse(event.data);if(data.type==='gesture'&&data.gesture)renderGesture(data.gesture)}catch{}};
 socket.onclose=()=>setTimeout(connectGestureStream,2000);
}
connectGestureStream();
$('gestureDebounceRange').oninput=()=>editGestureInterval($('gestureDebounceRange').value);
$('gestureDebounce').oninput=()=>editGestureInterval($('gestureDebounce').value);
$('saveGestureInterval').onclick=saveGestureInterval;
$('resetGestureInterval').onclick=()=>{editGestureInterval('0.5');saveGestureInterval()};

$('access').onclick=()=>action(async()=>{const r=await api('/api/request-access');notice(r.allowed?'已取得控制權限。':'請在系統設定的「裝置控制和資料取用」開啟 QRing Studio 權限，再回來啟用滑鼠。')});

$('readSelected').onclick=()=>action(async()=>{const r=await api('/api/read',{feature:$('readQuery').value});notice((labels[r.feature]||r.feature)+'：'+r.status)});

const directionNames={right:'向右',left:'向左',up:'向上',down:'向下'};
let directionRangesDirty=false;
function editDirectionRange(key,value){
 directionRangesDirty=true;
 $(key==='neutral'?'neutralZone':'directionRange-'+key).value=value;
 $(key==='neutral'?'neutralSlider':'directionSlider-'+key).value=value;
}
function renderDirectionRanges(s){
 const c=s.control||{},age=c.sample_age;
 const names={...directionNames,neutral:'中立停止',free:'自由方向',outside:'超出方向範圍',invalid:'姿勢資料無效',waiting:'等待方向取樣'};
 text($('directionStatus'),!s.connected?'尚未連接戒指':(names[c.direction]||'等待方向取樣')+(age==null?'':age>.35?' · 上次取樣 '+age.toFixed(1)+' 秒前':' · 最新取樣'));
 const saved=[];
 for(const [key,label]of Object.entries(directionNames)){
  const value=s.options['direction_range_'+key]??20;
  if(!directionRangesDirty){$('directionRange-'+key).value=value;$('directionSlider-'+key).value=value}
  const deviation=c.deviations?.[key];
  text($('directionLive-'+key),deviation==null?'等待取樣':`偏差 ${deviation.toFixed(1)}°／已套用 ${value}°`);
  $('directionRow-'+key).classList.toggle('matched',s.connected&&c.direction===key);
  saved.push(label+' '+value+'°');
 }
 if(!directionRangesDirty){$('neutralZone').value=s.options.neutral_zone??8;$('neutralSlider').value=s.options.neutral_zone??8}
 text($('neutralLive'),c.tilt==null?'回到中立姿勢附近即停止。':`距中立 ${c.tilt.toFixed(1)}°／停止區 ${s.options.neutral_zone??8}°`);
 text($('savedDirectionRanges'),'目前套用：'+saved.join('、')+'；中立 '+(s.options.neutral_zone??8)+'°'+(directionRangesDirty?' · 調整尚未儲存':''));
}
async function saveDirectionRanges(){
 const changes={};
 for(const key of [...Object.keys(directionNames),'neutral']){
  const input=$(key==='neutral'?'neutralZone':'directionRange-'+key),value=Number(input.value),low=key==='neutral'?0:2,high=key==='neutral'?20:60;
  if(input.value===''||!Number.isFinite(value)||value<low||value>high){notice((key==='neutral'?'中立停止區':directionNames[key]+'容許偏差')+`請輸入 ${low}–${high} 度。`);return}
  changes[key==='neutral'?'neutral_zone':'direction_range_'+key]=value;
 }
 $('saveDirectionRanges').disabled=true;$('resetDirectionRanges').disabled=true;
 try{await api('/api/options',changes);directionRangesDirty=false;await refresh();notice('方向範圍已套用並儲存，不必重新校正。')}
 catch(e){notice(e.message)}finally{$('saveDirectionRanges').disabled=false;$('resetDirectionRanges').disabled=false}
}
for(const key of [...Object.keys(directionNames),'neutral']){
 const slider=$(key==='neutral'?'neutralSlider':'directionSlider-'+key),input=$(key==='neutral'?'neutralZone':'directionRange-'+key);
 slider.oninput=()=>editDirectionRange(key,slider.value);input.oninput=()=>editDirectionRange(key,input.value);
}
$('saveDirectionRanges').onclick=saveDirectionRanges;
$('resetDirectionRanges').onclick=()=>{for(const key of Object.keys(directionNames))editDirectionRange(key,20);editDirectionRange('neutral',8);saveDirectionRanges()};
