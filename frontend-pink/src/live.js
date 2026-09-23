const enabled=new URLSearchParams(location.search).get('live')==='1';
const id=()=>crypto.randomUUID();
const escape=text=>String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const live={enabled,version:-1,state:null,onState:()=>{},onMessage:()=>{}};
let polling=null,queue=Promise.resolve(),mic=null,cam=null;
const seenClarifications=new Set();

async function api(path,body,method) {
  const response=await fetch('/api/live'+path,{method:method||(body===undefined?'GET':'POST'),headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'请求失败，请重试');
  return data;
}
const status=message=>{const el=document.querySelector('#live-status');if(el)el.textContent=message;};
const fail=error=>{status(error.message||String(error));live.onMessage(error.message||String(error));};

live.refresh=async()=>{
  if(polling)await polling;
  let finish;polling=new Promise(resolve=>{finish=resolve;});
  try{
    const state=await api('/state');
    if(state.version>=live.version){live.state=state;
      if(state.version!==live.version){live.version=state.version;live.onState(state);}
      showActivity(state);
      const item=state.clarifications.find(e=>!e.cancelled&&!seenClarifications.has(e.id));
      const dialog=document.querySelector('#live-time-dialog');
      if(item&&!dialog.open){seenClarifications.add(item.id);openClarification(item);}
    }
  }finally{polling=null;finish();}
};
live.changeSteps=(task,updates)=>{
  queue=queue.catch(()=>{}).then(async()=>{await api('/tasks/'+task+'/steps',{event_id:id(),updates},'PATCH');await live.refresh();});
  return queue;
};
live.editItem=item=>openClarification(live.state.events.find(e=>e.id===item));
live.changeItem=(item,body)=>api('/items/'+item,body,'PATCH').then(()=>live.refresh());
live.addItem=body=>api('/items',body).then(()=>live.refresh());

function showActivity(state){
  const latest=state.activity.at(-1), el=document.querySelector('#live-result');
  if(latest)el.textContent=[latest.text?`听到：${latest.text}`:'',latest.reply,latest.observation].filter(Boolean).join('\n');
  const t=latest?.timings;
  document.querySelector('#live-latency').textContent=t?[
    t.asr_ms!==undefined?`转写 ${(t.asr_ms/1000).toFixed(1)} 秒`:'',
    `模型 ${((t.model_ms||0)/1000).toFixed(1)} 秒`,
    t.capture_to_ui_ms!==undefined?`拍照到显示 ${(t.capture_to_ui_ms/1000).toFixed(1)} 秒`:''
  ].filter(Boolean).join(' · '):'识别后会显示实际耗时';
  const commands=state.commands.filter(c=>c.status==='queued');
  document.querySelector('#live-device').textContent=(state.hardware.connected?'硬件网关已连接':'硬件网关未连接')+` · ${commands.length} 组提醒待执行`+(state.hardware.haptic?'':' · 尚无可用马达');
  const pending=state.clarifications.filter(e=>!e.cancelled);
  const button=document.querySelector('#live-pending');button.hidden=!pending.length;
  button.textContent=`补充 ${pending.length} 件事项的时间`;
}

function openClarification(item){
  const d=document.querySelector('#live-time-dialog'),f=d.querySelector('form');
  f.dataset.item=item.id;f.elements.title.value=item.title;d.querySelector('h2').textContent=`什么时候${item.kind==='reminder'?'提醒':'安排'}「${item.title}」？`;
  f.elements.date.value=item.date||'';f.elements.time.value=item.time||'';
  f.elements.time.required=item.kind==='reminder';f.querySelector('[data-time]').hidden=item.kind!=='reminder';d.showModal();
}

async function startMic(){
  if(mic)return;
  if(!navigator.mediaDevices||!globalThis.AudioWorkletNode)throw new Error('当前浏览器不支持实时采集，请用 Chrome 打开本机地址');
  let stream,ctx,ws;
  try{
    stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    ctx=new AudioContext();await ctx.resume();
    await ctx.audioWorklet.addModule(new URL('./pcm-worklet.js',import.meta.url));
    ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/live/audio`);
    await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=()=>reject(new Error('语音连接失败'));});
    const source=ctx.createMediaStreamSource(stream),processor=new AudioWorkletNode(ctx,'mindloop-pcm');
    const silence=ctx.createGain();silence.gain.value=0;source.connect(processor);processor.connect(silence).connect(ctx.destination);
    processor.port.onmessage=e=>{if(e.data==='flushed'){mic?.flushed?.();return;}if(ws.readyState===WebSocket.OPEN)ws.send(e.data);};
    mic={stream,ctx,ws,processor};
    ws.onmessage=async e=>{const m=JSON.parse(e.data);
      if(m.type==='ready')status('正在听 · 说完一句就处理');
      if(m.type==='sentence')status('这句话已提交，仍可继续说');
      if(m.type==='processing')status('正在识别 · 麦克风继续采集');
      if(m.type==='result'){status(m.reply);live.onMessage(m.reply);await live.refresh();}
      if(m.type==='error')fail(new Error(m.message));
    };
    ws.onclose=()=>{if(mic?.ws===ws){stopMic(false);status('语音连接已关闭，请重新开启');}};
    document.querySelector('#live-mic').textContent='停止倾听';document.querySelector('#live-mic').setAttribute('aria-pressed','true');
    status('正在听 · 停顿约 0.6 秒就提交');
  }catch(error){stream?.getTracks().forEach(t=>t.stop());await ctx?.close();ws?.close();throw error;}
}
async function stopMic(flush=true){
  if(!mic)return;
  const m=mic;
  if(m.stopping)return;m.stopping=true;
  if(flush)await new Promise(resolve=>{m.flushed=resolve;m.processor.port.postMessage('flush');setTimeout(resolve,200);});
  mic=null;m.processor.disconnect();m.stream.getTracks().forEach(t=>t.stop());await m.ctx.close();
  if(flush&&m.ws.readyState===WebSocket.OPEN)m.ws.send(JSON.stringify({type:'stop'}));else m.ws.close();
  document.querySelector('#live-mic').textContent='开启倾听';document.querySelector('#live-mic').setAttribute('aria-pressed','false');
  if(flush)status('已停止采集，正在处理最后一句');
}

async function startCamera(){
  if(cam)return;
  const video=document.querySelector('#live-video');let stream,session;
  try{
    stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:960},height:{ideal:540},facingMode:{ideal:'environment'}}});
    video.srcObject=stream;video.hidden=false;await video.play();
    session=await api('/camera/start',{});
    cam={stream,session:session.session_id,busy:false,timer:null,pending:null};const current=cam;
    const send=async frame=>{
      if(cam!==current)return;
      if(current.busy){current.pending=frame;return;}
      current.busy=true;
      try{
        const result=await api('/image',{event_id:id(),session_id:current.session,...frame.payload});
        if(cam!==current)return;
        status(result.reply||'画面已识别');await live.refresh();
        await new Promise(requestAnimationFrame);
        await api('/latency',{event_id:result.event_id,capture_to_ui_ms:performance.now()-frame.started});
      }catch(error){if(cam===current)fail(error);}
      finally{current.busy=false;const next=current.pending;current.pending=null;if(next&&cam===current)send(next);}
    };
    const capture=()=>{
      if(!video.videoWidth||cam!==current)return;
      const started=performance.now(),canvas=document.createElement('canvas');
      canvas.width=Math.min(960,video.videoWidth);canvas.height=Math.round(video.videoHeight*canvas.width/video.videoWidth);
      canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
      send({started,payload:{captured_at:new Date().toISOString(),image:canvas.toDataURL('image/jpeg',0.75)}});
    };
    capture();current.timer=setInterval(capture,5000);
    document.querySelector('#live-camera').textContent='关闭摄像头';document.querySelector('#live-camera').setAttribute('aria-pressed','true');
    status('摄像头已开启 · 每 5 秒取图');
  }catch(error){stream?.getTracks().forEach(t=>t.stop());video.srcObject=null;video.hidden=true;if(session)await api('/camera/stop',{session_id:session.session_id});throw error;}
}
async function stopCamera(){
  if(!cam)return;
  const c=cam;cam=null;clearInterval(c.timer);c.stream.getTracks().forEach(t=>t.stop());
  document.querySelector('#live-video').srcObject=null;document.querySelector('#live-video').hidden=true;
  document.querySelector('#live-camera').textContent='开启摄像头';document.querySelector('#live-camera').setAttribute('aria-pressed','false');
  await api('/camera/stop',{session_id:c.session});status('摄像头已关闭');
}

live.init=async()=>{
  if(!enabled)return;
  const panel=document.createElement('aside');panel.className='live-panel';
  panel.innerHTML=`<details><summary>实时陪伴 <span>语音 · 摄像头</span></summary><div class="live-body"><p id="live-status" role="status" aria-live="polite">正在连接…</p><div class="live-controls"><button id="live-mic" aria-pressed="false">开启倾听</button><button id="live-camera" aria-pressed="false">开启摄像头</button></div><p class="live-note">开启后，语音和画面会用于模型识别。关闭即可停止采集。</p><video id="live-video" autoplay muted playsinline hidden aria-label="摄像头预览"></video><form id="live-text-form"><label for="live-text">也可以直接告诉我</label><div class="live-text-row"><input id="live-text" required maxlength="1000" placeholder="帮我开始写报告"><button type="submit">发送</button></div></form><button id="live-pending" hidden></button><p id="live-result" role="status"></p><p id="live-latency" class="live-note"></p><p id="live-device" class="live-note"></p></div></details>`;
  document.body.append(panel);
  const d=document.createElement('dialog');d.id='live-time-dialog';
  d.innerHTML=`<form><h2></h2><label>事项<input name="title" required maxlength="160"></label><label>日期<input name="date" type="date" required></label><label data-time>提醒时间<input name="time" type="time"></label><div class="live-controls"><button type="button" data-later>稍后补充</button><button type="button" data-cancel>取消此提醒</button><button type="submit">保存时间</button></div></form>`;document.body.append(d);
  d.querySelector('[data-later]').onclick=()=>d.close();
  d.querySelector('[data-cancel]').onclick=async()=>{try{await live.changeItem(d.querySelector('form').dataset.item,{cancelled:true});d.close();}catch(error){fail(error);}};
  d.querySelector('form').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;
    try{await api('/items/'+f.dataset.item,{title:f.elements.title.value,date:f.elements.date.value,time:f.elements.time.value||null},'PATCH');d.close();await live.refresh();}catch(error){fail(error);}};
  document.querySelector('#live-pending').onclick=()=>openClarification(live.state.clarifications.find(e=>!e.cancelled));
  document.querySelector('#live-mic').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{await (mic?stopMic():startMic());}catch(error){fail(error);}finally{b.disabled=false;}};
  document.querySelector('#live-camera').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{await (cam?stopCamera():startCamera());}catch(error){fail(error);}finally{b.disabled=false;}};
  document.querySelector('#live-text-form').onsubmit=async e=>{
    e.preventDefault();const input=document.querySelector('#live-text'),button=e.currentTarget.querySelector('button');
    button.disabled=true;status('正在理解…');
    try{const result=await api('/text',{event_id:id(),text:input.value,captured_at:new Date().toISOString()});input.value='';status(result.reply);await live.refresh();}
    catch(error){fail(error);}finally{button.disabled=false;}
  };
  await live.refresh().then(()=>status('已连接 · 可以开启倾听或摄像头')).catch(fail);
  setInterval(()=>{if(!document.hidden)live.refresh().catch(()=>status('服务连接中断，请检查本机服务'));},1000);
  addEventListener('pagehide',()=>{
    stopMic(false);
    if(cam){navigator.sendBeacon('/api/live/camera/stop',new Blob([JSON.stringify({session_id:cam.session})],{type:'application/json'}));cam.stream.getTracks().forEach(t=>t.stop());}
  });
};
