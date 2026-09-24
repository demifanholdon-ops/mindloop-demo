"""Real S3 -> BLE -> nRF handshake and screen test (changes the screen).

Run from mindloop_v0_3: .venv/bin/python scripts/test_s3_ble.py --port PORT
Optional --buttons waits for k1 single, k2 single and k2 long.
"""
import argparse
import json
import time
import serial
from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--buttons', action='store_true')
    args = parser.parse_args()
    with serial.Serial(args.port, 115200, timeout=.25) as link:
        def send(payload):
            link.write((json.dumps({'cmd': 'ble_send', 'payload': payload}) + '\n').encode())

        def wait_for(predicate, timeout):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                raw = link.readline()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except (ValueError, UnicodeError):
                    continue
                print(json.dumps(event, ensure_ascii=False), flush=True)
                if predicate(event):
                    return event
            raise TimeoutError(f'Expected BLE response not received in {timeout}s')

        send({'cmd': 'hello'})
        ready = wait_for(lambda e: e.get('event') == 'wearable' and
                         e.get('payload', {}).get('event') == 'ready', 30)
        assert ready['payload'].get('display') is True, ready
        image = Image.new('1', (160, 80), 0)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 159, 79), outline=1)
        draw.text((10, 10), 'MindLoop BLE OK', fill=1)
        draw.text((10, 30), 'S3 -> nRF screen', fill=1)
        draw.text((10, 50), 'K1 / K2 / hold K2', fill=1)
        frame_id = int(time.time()) % 1000000000
        started = time.monotonic()
        send({'cmd': 'frame', 'id': frame_id, 'hex': image.tobytes().hex()})
        wait_for(lambda e: e.get('event') == 'wearable' and
                 e.get('payload', {}).get('event') == 'displayed' and
                 e['payload'].get('id') == frame_id, 30)
        print(f'PASS: hello + frame acknowledgement ({time.monotonic()-started:.3f}s). '
              'Visual screen inspection is still required.', flush=True)
        if args.buttons:
            remaining = {('k1', 'single'), ('k2', 'single'), ('k2', 'long')}
            def got_all(event):
                p = event.get('payload', {})
                if event.get('event') == 'wearable' and p.get('event') == 'button':
                    remaining.discard((p.get('key'), p.get('gesture')))
                    print('Remaining gestures:', sorted(remaining), flush=True)
                return not remaining
            wait_for(got_all, 120)
            print('PASS: all three physical button gestures received via S3 BLE')


if __name__ == '__main__':
    main()
