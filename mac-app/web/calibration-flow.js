(function(root){
  const unit=v=>{const n=Math.hypot(...v);if(n<.01)throw Error('姿勢資料無效');return v.map(x=>x/n)};
  const dot=(a,b)=>a.reduce((sum,x,i)=>sum+x*b[i],0);
  function directionCheck(pose,step,poses){
    if(step===0)return;
    const n=unit(poses[0]);
    const tangent=v=>{const g=unit(v),d=dot(g,n);if(d>Math.cos(8*Math.PI/180)||d<.5)throw Error('請從中立姿勢傾斜約 10–60 度');return unit(g.map((x,i)=>x-d*n[i]))};
    const current=tangent(pose);
    if(step===2&&dot(tangent(poses[1]),current)>-.2)throw Error('向左姿勢須與向右相反');
    if(step===3){const right=unit(tangent(poses[1]).map((x,i)=>x-tangent(poses[2])[i]));if(1-dot(right,current)**2<.2)throw Error('向上姿勢須與左右方向分開');}
    if(step===4&&dot(tangent(poses[3]),current)>-.2)throw Error('向下姿勢須與向上相反');
  }
  function evaluatePose(samples,now,step,poses){
    const available=samples.filter(s=>s.time<=now);
    const boundary=available.length?available.at(-1).time-3000:now;
    let start=available.findIndex(s=>s.time>=boundary);
    if(start>0)start--;
    const ss=start>=0?available.slice(start):[];
    const span=ss.length?ss.at(-1).time-ss[0].time:0;
    const result={ready:false,progress:Math.min(1,span/3000),pose:null,reason:'保持姿勢約 3 秒，準備好後單擊戒指確認'};
    if(!ss.length||now-ss.at(-1).time>750){result.reason='等待新的戒指資料';return result;}
    if(ss.some((s,i)=>i&&(s.time-ss[i-1].time<0||s.time-ss[i-1].time>1000))){result.reason='資料暫時不連續，請保持姿勢等待';return result;}
    if(ss.length<6||span<3000)return result;
    const mean=ss[0].v.map((_,i)=>ss.reduce((sum,s)=>sum+s.v[i],0)/ss.length);
    const spread=Math.max(...mean.map((m,i)=>Math.sqrt(ss.reduce((sum,s)=>sum+(s.v[i]-m)**2,0)/ss.length)));
    if(spread>.035){result.reason='手指仍在移動，請保持這個姿勢';return result;}
    try{result.pose=unit(mean);directionCheck(result.pose,step,poses);result.ready=true;result.progress=1;result.reason='姿勢已穩定，單擊戒指確認並前往下一步';}
    catch(e){result.reason=e.message;}
    return result;
  }
  function canConfirmGesture(event,context){
    if(event.code!==3||event.calibration!==true||!context.connected||!context.visible||context.busy)return false;
    if(context.now-context.lastConfirmation<1000)return false;
    const g=event.gesture;
    if(!g||!Number.isInteger(g.sequence)||g.sequence<=context.lastSequence)return false;
    const age=context.wallNow-Date.parse(g.time);
    return Number.isFinite(age)&&age>=-2000&&age<=2000;
  }
  const api={evaluatePose,canConfirmGesture};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.CalibrationFlow=api;
})(typeof window==='undefined'?globalThis:window);
