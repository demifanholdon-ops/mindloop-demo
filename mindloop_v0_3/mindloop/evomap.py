import os, hashlib
import httpx

class EvoMapAdapter:
    def __init__(self):
        self.url = os.getenv('EVOMAP_PUBLISH_URL', '').strip()
        self.key = os.getenv('EVOMAP_API_KEY', '').strip()

    def export(self, completed_actions, feedback_counts):
        safe = [x for x in completed_actions if isinstance(x, str) and x.strip()][-5:]
        sid = hashlib.sha256(('|'.join(safe) or 'empty').encode()).hexdigest()[:16]
        return {
            'type': 'mindloop_strategy_asset',
            'version': '0.1',
            'strategy_id': 'ml-' + sid,
            'context': 'task_initiation_or_attention_drift',
            'principle': 'minimum_intervention_maximum_behavioral_effect',
            'successful_atomic_actions': safe,
            'feedback_counts': feedback_counts,
            'privacy': {
                'contains_name': False,
                'contains_audio': False,
                'contains_raw_video': False,
                'contains_location': False,
            },
        }

    async def publish(self, asset):
        if not self.url:
            return {'ok': False, 'mode': 'dry_run', 'reason': 'EVOMAP_PUBLISH_URL not configured', 'asset': asset}
        headers = {'Content-Type': 'application/json'}
        if self.key:
            headers['Authorization'] = 'Bearer ' + self.key
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(self.url, headers=headers, json=asset)
            r.raise_for_status()
            try:
                body = r.json()
            except Exception:
                body = {'text': r.text}
            return {'ok': True, 'mode': 'published', 'response': body}
