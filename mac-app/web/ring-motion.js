/* Calibration preview uses the same angular regions as the native mouse controller. */
(function(root){
 const dot=(a,b)=>a.reduce((sum,x,i)=>sum+x*b[i],0);
 const unit=v=>{const n=Math.hypot(...v);return v.map(x=>x/n)};
 const angle=(a,b)=>Math.acos(Math.max(-1,Math.min(1,dot(a,b))))*180/Math.PI;
 function target(raw,poses,axes,limit,settings={}){
  const norm=Math.hypot(...raw)/8192;
  if(norm<.8||norm>1.2)return {velocity:[0,0],direction:'invalid'};
  const g=unit(raw),[n,r,u]=axes,den=dot(g,n),tilt=angle(g,n),dead=settings.neutral_zone??8;
  if(tilt<=dead)return {velocity:[0,0],direction:'neutral'};
  const names=poses.length===5?['right','left','up','down']:['right','up'];
  const deviations=Object.fromEntries(names.map((name,i)=>[name,angle(g,unit(poses[i+1]))]));
  const matches=names.filter(name=>deviations[name]<=(settings['direction_range_'+name]??20));
  if(den<.5&&!matches.length)return {velocity:[0,0],direction:'outside'};
  matches.sort((a,b)=>deviations[a]-deviations[b]);
  const sp=degrees=>Math.sign(degrees)*limit*Math.max(0,Math.min(1,(Math.abs(degrees)-dead)/27))**2;
  const direction=matches[0]||'free',magnitude=sp(tilt);
  const velocity=({right:[magnitude,0],left:[-magnitude,0],up:[0,-magnitude],down:[0,magnitude]})[direction]||
    [sp(Math.atan2(dot(g,r),den)*180/Math.PI),-sp(Math.atan2(dot(g,u),den)*180/Math.PI)];
  return {velocity,direction,deviations,tilt};
 }
 const api={target};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.RingMotion=api;
})(typeof globalThis!=='undefined'?globalThis:this);
