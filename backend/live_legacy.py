"""EvoMap interaction adapter over the same tasks used by the pink App."""
import base64
import io
import wave

from PIL import Image


def validate_image(image):
    if not image:
        return None
    try:
        header, payload = image.split(',', 1)
        if header != 'data:image/jpeg;base64' or len(payload) > 1500000:
            raise ValueError()
        picture = Image.open(io.BytesIO(base64.b64decode(payload, validate=True)))
        if max(picture.size) > 1280:
            raise ValueError()
        picture.verify()
    except Exception:
        raise ValueError('请提供最长边不超过1280像素的有效JPEG画面') from None
    return image


def pcm_wav(encoded):
    try:
        pcm = base64.b64decode(encoded, validate=True)
        if not pcm or len(pcm) % 2 or len(pcm) > 16000 * 2 * 15:
            raise ValueError()
    except Exception:
        raise ValueError('录音应为16kHz单声道PCM16，最长15秒') from None
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    return output.getvalue()


def session(store):
    task = store.task(store.data['active_task_id'])
    pending = next((s for s in task['steps'] if not s['done']), None) if task else None
    return {'state': 'idle' if not task else 'action_ready' if pending else 'completed',
            'task_id': task['id'] if task else None,
            'current_step': pending,
            'can_resume': bool(store.task(store.data.get('hardware_last_task_id')))}


def action_for(state, key, gesture, recording=False):
    # Mirrors EvoMap hardware_bridge.py, including state-dependent K1/K2.
    if recording:
        return 'record_stop' if (key, gesture) == ('k1', 'single') else 'ignore'
    if state == 'idle':
        return {('k1', 'single'): 'record_start', ('k2', 'long'): 'resume'}.get((key, gesture), 'ignore')
    if state == 'completed':
        return {('k1', 'single'): 'new', ('k2', 'single'): 'redo'}.get((key, gesture), 'ignore')
    return {('k1', 'single'): 'done', ('k1', 'double'): 'undo', ('k1', 'long'): 'new',
            ('k2', 'single'): 'stuck', ('k2', 'double'): 'help'}.get((key, gesture), 'ignore')


def apply_button(store, action):
    current = session(store)
    task = store.task(current['task_id'])
    if action == 'new':
        if task:
            store.data['hardware_last_task_id'] = task['id']
        store.data['active_task_id'] = None
    elif action == 'resume':
        task = store.task(store.data.get('hardware_last_task_id'))
        if not task:
            raise ValueError('没有可恢复的任务')
        store.data['active_task_id'] = task['id']
        if all(s['done'] for s in task['steps']):
            store.set_steps(task['id'], [{'step_id': task['steps'][-1]['id'], 'done': False}], 'app')
    elif action in {'done', 'undo', 'redo'}:
        if not task:
            raise ValueError('当前没有任务')
        if action == 'done':
            step = current['current_step']
        elif action == 'redo':
            step = task['steps'][-1]
        else:
            index = next((i for i, s in enumerate(task['steps']) if not s['done']), len(task['steps']))
            if index <= 0:
                raise ValueError('已是第一步，无法撤回')
            step = task['steps'][index - 1]
        if step:
            store.set_steps(task['id'], [{'step_id': step['id'], 'done': action == 'done'}], 'app')
    return session(store)
