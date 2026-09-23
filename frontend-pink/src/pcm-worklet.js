class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super(); this.pending=[]; this.cursor=0; this.output=[];
    this.port.onmessage=e=>{if(e.data==='flush'){
      if(this.output.length){const pcm=new Int16Array(this.output);this.port.postMessage(pcm.buffer,[pcm.buffer]);this.output=[];}
      this.port.postMessage('flushed');
    }};
  }
  process(inputs) {
    const channel=inputs[0]?.[0];
    if (!channel) return true;
    this.pending.push(...channel);
    const ratio=sampleRate/16000;
    while (this.cursor+ratio<=this.pending.length) {
      const index=Math.floor(this.cursor);
      // Linear interpolation keeps the fractional resampling phase between callbacks.
      const fraction=this.cursor-index;
      const a=this.pending[index], b=this.pending[Math.min(index+1,this.pending.length-1)];
      this.output.push(Math.round(Math.max(-1,Math.min(1,a+(b-a)*fraction))*32767));
      this.cursor+=ratio;
      if(this.output.length===1600){const pcm=new Int16Array(this.output);this.port.postMessage(pcm.buffer,[pcm.buffer]);this.output=[];}
    }
    const consumed=Math.floor(this.cursor);
    this.pending.splice(0,consumed);this.cursor-=consumed;
    return true;
  }
}
registerProcessor('mindloop-pcm',PcmCapture);
