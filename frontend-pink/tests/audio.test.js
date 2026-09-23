import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';

test('worklet resamples continuous 48k PCM to 16k and flushes the last packet',()=>{
  let Processor;
  const messages=[];
  const context={sampleRate:48000,Int16Array,Math,
    AudioWorkletProcessor:class {constructor(){this.port={postMessage:x=>messages.push(x)};}},
    registerProcessor:(name,klass)=>{Processor=klass;}};
  vm.runInNewContext(fs.readFileSync(new URL('../src/pcm-worklet.js',import.meta.url),'utf8'),context);
  const p=new Processor();
  // 150 ms of signal deliberately does not end at a 100 ms network boundary.
  for(let i=0;i<7200;i+=128)p.process([[new Float32Array(Math.min(128,7200-i)).fill(.25)]]);
  p.port.onmessage({data:'flush'});
  assert.equal(messages.at(-1),'flushed');
  const packets=messages.slice(0,-1).map(x=>new Int16Array(x));
  assert.equal(packets.reduce((n,x)=>n+x.length,0),2400);
  assert.equal(packets[0].length,1600);
  assert.equal(packets[1].length,800);
  assert.equal(packets[0][0],8192);
});
