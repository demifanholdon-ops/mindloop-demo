// Current EvoMap flow: one recording and optional current image per task.
export function taskCapture({api,status,refresh,onMessage}){
  let mic=null,camera=null,busy=false,remoteTimer=null,remoteStarting=false;
  const video=document.querySelector('#live-video');
  const enabled=()=>document.querySelector('#task-use-camera').checked;
  const report=e=>{status(e.message||String(e));onMessage(e.message||String(e));};
  async function openCamera(){
    if(camera)return;
    const selected=document.querySelector('#task-camera-device').value;
    const stream=await navigator.mediaDevices.getUserMedia({video:selected?{deviceId:{exact:selected},width:{ideal:640}}:{width:{ideal:640}}});
    camera=stream;video.srcObject=stream;video.hidden=false;await video.play();
    const devices=await navigator.mediaDevices.enumerateDevices();
    const select=document.querySelector('#task-camera-device');
    select.replaceChildren(new Option('默认摄像头',''));
    for(const d of devices.filter(d=>d.kind==='videoinput'))select.add(new Option(d.label||'摄像头',d.deviceId));
    select.value=selected;
  }
  function picture(){
    if(!camera||!video.videoWidth)return null;
    const canvas=document.createElement('canvas');canvas.width=Math.min(video.videoWidth,640);
    canvas.height=Math.round(video.videoHeight*canvas.width/video.videoWidth);
    canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);
    return canvas.toDataURL('image/jpeg',.75);
  }
  function closeCamera(){camera?.getTracks().forEach(t=>t.stop());camera=null;video.srcObject=null;video.hidden=true;}
  async function submit(body){
    busy=true;status('正在转写、理解并生成步骤…');
    try{const result=await api('/legacy/task',{event_id:crypto.randomUUID(),...body});status(result.reply);onMessage(result.reply);await refresh();}
    finally{busy=false;}
  }
  async function start(){
    if(busy||mic)return;
    busy=true;let stream,ctx;
    try{
      if(enabled())await openCamera();
      stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
      ctx=new AudioContext();await ctx.resume();await ctx.audioWorklet.addModule(new URL('./pcm-worklet.js',import.meta.url));
      const source=ctx.createMediaStreamSource(stream),processor=new AudioWorkletNode(ctx,'mindloop-pcm'),silent=ctx.createGain();
      silent.gain.value=0;source.connect(processor);processor.connect(silent).connect(ctx.destination);
      const current={stream,ctx,processor,chunks:[],length:0,timer:null};mic=current;
      processor.port.onmessage=e=>{
        if(e.data==='flushed'){current.flushed?.();return;}
        const data=new Uint8Array(e.data),remaining=480000-current.length;
        if(remaining>0){const part=data.slice(0,remaining);current.chunks.push(part);current.length+=part.length;}
      };
      current.timer=setTimeout(()=>stop().catch(report),15000);
      document.querySelector('#live-mic').textContent='结束录音并创建';
      document.querySelector('#live-mic').setAttribute('aria-pressed','true');
      status('正在录音，结束后创建任务 · 最长15秒');
    }catch(e){stream?.getTracks().forEach(t=>t.stop());await ctx?.close();closeCamera();throw e;}
    finally{busy=false;}
  }
  async function stop(send=true){
    if(!mic||mic.stopping)return;
    const current=mic;current.stopping=true;clearTimeout(current.timer);
    if(send)await new Promise(resolve=>{current.flushed=resolve;current.processor.port.postMessage('flush');setTimeout(resolve,200);});
    const image=send?picture():null;mic=null;
    current.processor.disconnect();current.stream.getTracks().forEach(t=>t.stop());await current.ctx.close();closeCamera();
    document.querySelector('#live-mic').textContent='录音创建任务';document.querySelector('#live-mic').setAttribute('aria-pressed','false');
    if(send){
      const bytes=new Uint8Array(current.length);let offset=0;
      for(const chunk of current.chunks){bytes.set(chunk,offset);offset+=chunk.length;}
      let raw='';for(let i=0;i<bytes.length;i+=8192)raw+=String.fromCharCode(...bytes.subarray(i,i+8192));
      await submit({pcm:btoa(raw),image});
    }
  }
  async function text(goal){
    if(busy||mic)throw new Error('请先结束当前录音或等待生成完成');
    busy=true;
    try{if(enabled())await openCamera();const image=picture();closeCamera();await submit({text:goal,image});}
    finally{closeCamera();busy=false;}
  }
  async function button(key,gesture){
    if(busy)return;
    const result=await api('/legacy/button',{event_id:crypto.randomUUID(),key,gesture,recording:!!mic});
    if(result.action==='record_start')await start();
    else if(result.action==='record_stop')await stop();
    else {status(result.reply);await refresh();}
  }
  async function sync(state){
    // Only cache images locally during an actual hardware recording (max 15s).
    if(state.session?.recording&&enabled()&&!mic&&!remoteTimer&&!remoteStarting){
      remoteStarting=true;
      try{await openCamera();const upload=()=>{const image=picture();if(image)api('/legacy/frame',{image}).catch(report);};upload();remoteTimer=setInterval(upload,2000);}
      catch(e){report(e);}finally{remoteStarting=false;}
    }else if(!state.session?.recording&&remoteTimer){clearInterval(remoteTimer);remoteTimer=null;closeCamera();}
  }
  function dispose(){stop(false);clearInterval(remoteTimer);remoteTimer=null;closeCamera();}
  return {toggle:()=>mic?stop():start(),text,button,sync,dispose,
    disableCamera:()=>{clearInterval(remoteTimer);remoteTimer=null;closeCamera();api('/legacy/frame',{image:null}).catch(report);}};
}
