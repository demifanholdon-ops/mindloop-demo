class WearableSimulator:
    def __init__(self):
        self.state = {'light': 'off', 'haptic': 'none', 'voice': None}

    def intervene(self, cognitive_state, repeated_stuck=0):
        if cognitive_state == 'drift':
            out = {'channel': 'haptic', 'pattern': 'double_soft'}
        elif cognitive_state == 'focus':
            out = {'channel': 'light', 'pattern': 'focus'}
        elif cognitive_state == 'completed':
            out = {'channel': 'haptic', 'pattern': 'success'}
        elif repeated_stuck > 0:
            out = {'channel': 'voice', 'pattern': 'gentle', 'text': '只做屏幕上这一小步。'}
        else:
            out = {'channel': 'haptic', 'pattern': 'short'}

        if out['channel'] == 'haptic':
            self.state['haptic'] = out['pattern']
        elif out['channel'] == 'light':
            self.state['light'] = out['pattern']
        elif out['channel'] == 'voice':
            self.state['voice'] = out.get('text')
        out['device_snapshot'] = dict(self.state)
        return out
