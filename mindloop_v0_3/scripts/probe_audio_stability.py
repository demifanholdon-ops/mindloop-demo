"""USB audio stability probe. Stop the hardware bridge first; no audio saved."""
import serial,time,json,sys
mode=sys.argv[1] if len(sys.argv)>1 else 'plain'
duration=float(sys.argv[2]) if len(sys.argv)>2 else 6
port=sys.argv[3] if len(sys.argv)>3 else '/dev/cu.usbmodem1101'
with serial.Serial(port,115200,timeout=.15) as s:
 def send(d):s.write((json.dumps(d)+'\n').encode())
 send({'cmd':'hello'})
 print('handshake',s.readline().decode().strip(),flush=True)
 send({'cmd':'record','action':'start'})
 start=time.monotonic();stop=False;chunks=0;last=-1;hello=start
 try:
  while time.monotonic()-start<duration+6:
   elapsed=time.monotonic()-start
   if elapsed>duration and not stop:send({'cmd':'record','action':'stop'});stop=True
   if mode in {'hello','frame'} and time.monotonic()-hello>2:send({'cmd':'hello'});hello=time.monotonic()
   raw=s.readline()
   if not raw:continue
   d=json.loads(raw)
   if d.get('event')=='audio_chunk':
    assert d['seq']==last+1,(last,d['seq'])
    chunks+=1;last=d['seq']
   else:
    print(round(elapsed,2),d,flush=True)
    if mode=='frame' and d.get('event')=='audio_start':
     send({'cmd':'frame','id':999,'hex':'00'*1600})
   if d.get('event')=='audio_stop':
    assert d.get('dropped',0)==0,d
    print('PASS chunks',chunks,flush=True);break
  else:raise RuntimeError('No audio_stop')
 except Exception as e:
  print('FAIL',mode,round(time.monotonic()-start,2),type(e).__name__,str(e),flush=True);raise
