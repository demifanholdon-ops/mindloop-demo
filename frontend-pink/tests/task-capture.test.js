import test from 'node:test';
import assert from 'node:assert/strict';
import {taskCapture} from '../src/task-capture.js';

test('task recording sends once after stop, releases microphone, and never opens continuous WebSocket',async()=>{
  const saved=new Map(['document','navigator','AudioContext','AudioWorkletNode','WebSocket'].map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
  const elements=new Map();
  for(const key of ['#live-video','#task-use-camera','#live-mic'])elements.set(key,{checked:false,setAttribute(){}});
  const tracks=[{stopped:false,stop(){this.stopped=true;}}];
  let processor,closed=false;
  const node=()=>({connect(){return this;},disconnect(){}});
  class Context{
    audioWorklet={addModule:async()=>{}};
    async resume(){}
    createMediaStreamSource(){return node();}
    createGain(){return {...node(),gain:{value:0}};}
    async close(){closed=true;}
  }
  class Worklet{
    constructor(){processor=this;this.port={postMessage:()=>this.port.onmessage({data:'flushed'})};}
    connect(){return this;}
    disconnect(){}
  }
  for(const [key,value] of Object.entries({
    document:{querySelector:selector=>elements.get(selector)},
    navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>tracks})}},
    AudioContext:Context,AudioWorkletNode:Worklet,
    WebSocket:class{constructor(){throw new Error('Continuous socket must stay off');}}
  }))Object.defineProperty(globalThis,key,{value,configurable:true});
  const calls=[];
  const capture=taskCapture({api:async(path,body)=>{calls.push({path,body});return {reply:'已创建'};},status(){},refresh:async()=>{},onMessage(){}});
  try{
    await capture.toggle();
    processor.port.onmessage({data:new Int16Array([123,456]).buffer});
    assert.equal(calls.length,0,'must not upload chunks or silence-delimited phrases while recording');
    await capture.toggle();
    assert.equal(calls.length,1);
    assert.equal(calls[0].path,'/legacy/task');
    assert.equal(Buffer.from(calls[0].body.pcm,'base64').length,4);
    assert.equal(calls[0].body.image,null);
    assert.ok(tracks.every(t=>t.stopped)&&closed);
  }finally{
    capture.dispose();
    for(const [key,descriptor] of saved){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}
  }
});
