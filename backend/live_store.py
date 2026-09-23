import copy
import json
import sqlite3
import re
import time
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")


def now():
    return datetime.now(TZ).isoformat(timespec="milliseconds")


def uid(prefix):
    return prefix + "_" + uuid4().hex[:16]


def check_date(value):
    if value:
        datetime.strptime(value, "%Y-%m-%d")
    return value


def check_clock(value):
    if value:
        datetime.strptime(value, "%H:%M")
    return value


def duration_seconds(title):
    numbers={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
    match=re.search(r'(\d+|[一二两三四五六七八九十])\s*(分钟|秒)',title)
    if not match: return 0
    number=int(match[1]) if match[1].isdigit() else numbers[match[1]]
    return number*(60 if match[2]=='分钟' else 1)


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, value TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, fingerprint TEXT, result TEXT)")
        row = self.db.execute("SELECT value FROM state WHERE id=1").fetchone()
        self.data = json.loads(row[0]) if row else {"version": 0, "tasks": [], "events": [], "drifts": [], "observations": [], "commands": [], "activity": [], "active_task_id": None}
        self.save()

    def save(self):
        self.data["version"] += 1
        self.db.execute("INSERT OR REPLACE INTO state VALUES (1,?)", (json.dumps(self.data, ensure_ascii=False),))
        self.db.commit()

    def receipt(self, event_id, fingerprint):
        row = self.db.execute("SELECT fingerprint,result FROM receipts WHERE id=?", (event_id,)).fetchone()
        if not row: return None
        if row[0] != fingerprint: raise ValueError("同一事件 ID 的内容发生变化")
        return json.loads(row[1])

    def remember(self, event_id, fingerprint, result):
        # Persist state and receipt together, no await in this transaction.
        self.data["version"] += 1
        self.db.execute("INSERT OR REPLACE INTO state VALUES (1,?)", (json.dumps(self.data, ensure_ascii=False),))
        self.db.execute("INSERT INTO receipts VALUES (?,?,?)", (event_id, fingerprint, json.dumps(result, ensure_ascii=False)))
        self.db.commit()

    def context(self):
        tasks = [t for t in self.data["tasks"] if t["id"] == self.data["active_task_id"] or any(not s['done'] for s in t['steps'])][-10:]
        return {"now": now(), "active_task_id": self.data["active_task_id"], "tasks": copy.deepcopy(tasks), "recent": copy.deepcopy(self.data["observations"][-18:]),
                "already_processed_speech": [{"text":a["text"],"already_saved":True} for a in self.data["activity"][-4:] if a.get("text")]}

    def snapshot(self):
        today = now()[:10]
        tasks = {}
        for task in self.data["tasks"]:
            last_completion = max((s.get('completed_at') or task['date'])[:10] for s in task['steps'])
            date = today if task["date"] < today and any(not s["done"] for s in task["steps"]) else max(task['date'],last_completion)
            tasks.setdefault(date, []).append(copy.deepcopy(task))
        focus = {today: {"total": 0, "returned": 0}}
        for d in self.data["drifts"]:
            f = focus.setdefault(d["at"][:10], {"total": 0, "returned": 0})
            f["total"] += 1
            if d.get('returned_at'):
                focus.setdefault(d['returned_at'][:10],{'total':0,'returned':0})['returned'] += 1
        events = copy.deepcopy(self.data["events"])
        for e in events:
            if e.get("date") and e["date"] < today and e["kind"] == "todo" and not e["done"]:
                e["original_date"] = e["date"]; e["date"] = today
        return {"version": self.data["version"], "anchor": today, "tasks": tasks, "events": events, "focus": focus,
                "active_task_id": self.data["active_task_id"], "activity": self.data["activity"][-8:],
                "clarifications": [e for e in events if e.get("needs_time") and not e.get('cancelled') and not e.get('done')],
                "commands": self.data["commands"][-10:]}

    def task(self, task_id):
        return next((t for t in self.data["tasks"] if t["id"] == task_id), None)

    def set_steps(self, task_id, updates, source, baseline=None):
        task = self.task(task_id)
        if not task: raise ValueError("任务不存在")
        by_id = {s["id"]: s for s in task["steps"]}
        if any(x["step_id"] not in by_id for x in updates): raise ValueError("步骤不属于此任务")
        changed = []
        for update in updates:
            step = by_id[update["step_id"]]
            if baseline is not None and baseline.get(step["id"]) != step["revision"]:
                continue  # Explicit user correction wins over in-flight inference.
            if step["done"] == update["done"]:
                if source == "app": step["revision"] += 1
                continue
            step.update(done=update["done"], revision=step["revision"]+1, source=source,
                        completed_at=now() if update["done"] else None,
                        time=datetime.now(TZ).strftime("%H:%M") if update["done"] else None)
            if source=='app': step.pop('visual_progress',None)
            changed.append(step["id"])
        return changed

    def add_item(self, item):
        d = item.copy()
        d["date"] = check_date(d.get("date"))
        d["time"] = check_clock(d.get("time"))
        if d.get("kind") not in {"todo", "reminder"}: raise ValueError("事项类型无效")
        for existing in self.data['events']:
            if existing.get('cancelled') or existing.get('done'): continue
            if (existing['title'].strip()==d['title'].strip() and existing['kind']==d['kind']
                and existing.get('recurrence')==d.get('recurrence')
                and (not d['date'] or d['date']==existing.get('date'))
                and (not d['time'] or d['time']==existing.get('time'))):
                return existing
        d.update(id=uid("item"), done=False, created_at=now(), cancelled=False)
        d["needs_time"] = not d["date"] or (d["kind"] == "reminder" and not d["time"])
        self.data["events"].append(d)
        return d

    def apply(self, decision, context, source, captured_at, text=None):
        # Validate all model dates before mutating any state.
        for item in decision.items:
            check_date(item.date); check_clock(item.time)
        changes = []
        if source != "vision":
            for new in decision.tasks:
                task = {"id": uid("task"), "title": new.title, "date": now()[:10], "note": "一步一步，已经在向前。",
                        "steps": [{"id": uid("step"), "title": s.title, "done": False, "revision": 0} for s in new.steps]}
                self.data["tasks"].append(task); self.data["active_task_id"] = task["id"]
            for item in decision.items:
                self.add_item(item.model_dump())
            if decision.returned: self.refocus()
        for task in context["tasks"]:
            base = {s["id"]: s["revision"] for s in task["steps"]}
            current=self.task(task['id'])
            permitted=set(base)
            if source=='vision':
                active={a.step_id for a in decision.activities if a.confidence>=.85}
                for step in current['steps']:
                    duration=duration_seconds(step['title'])
                    if not duration: continue
                    if base.get(step['id']) != step['revision']:
                        permitted.discard(step['id']);continue
                    progress=step.get('visual_progress')
                    if step['id'] not in active:
                        step.pop('visual_progress',None);permitted.discard(step['id']);continue
                    if not progress or (datetime.fromisoformat(captured_at)-datetime.fromisoformat(progress['last'])).total_seconds()>8:
                        progress={'since':captured_at,'last':captured_at}
                    progress['last']=captured_at;step['visual_progress']=progress
                    if (datetime.fromisoformat(captured_at)-datetime.fromisoformat(progress['since'])).total_seconds()<duration:
                        permitted.discard(step['id'])
            updates = [{"step_id": c.step_id, "done": True} for c in decision.completed
                       if c.step_id in permitted and c.confidence >= (0.85 if source == "vision" else 0.75)]
            changes += self.set_steps(task["id"], updates, source, base)
        if decision.observation:
            self.data["observations"].append({"at": captured_at, "source": source, "text": decision.observation})
            self.data["observations"] = self.data["observations"][-36:]
        return changes

    def drift(self, reason, at, session_id):
        d = {"id": uid("drift"), "at": at, "reason": reason, "returned_at": None}
        self.data["drifts"].append(d)
        self.data["commands"].append({"id": uid("cmd"), "drift_id": d["id"], "session_id": session_id,
                                      "kind": "haptic", "pattern_ms": [2000,2000,2000,2000,2000],
                                      "status": "queued", "created_at": now(), "device_executed": False})

    def refocus(self):
        latest = self.data["drifts"][-1] if self.data["drifts"] else None
        if latest and not latest["returned_at"]: latest["returned_at"] = now()

    def due_reminders(self, at=None):
        at = at or now()
        changed = False
        for item in self.data['events']:
            if item.get('cancelled') or item.get('done') or item.get('needs_time') or not item.get('time'): continue
            date = at[:10] if item.get('recurrence') == 'daily' and item['date'] <= at[:10] else item['date']
            due = date+'T'+item['time']
            if due > at[:16] or item.get('last_fired') == due: continue
            # Missed daily reminders are consolidated into today's occurrence.
            item['last_fired'] = due
            self.data['commands'].append({'id':uid('cmd'), 'item_id':item['id'], 'kind':'reminder',
                'pattern_ms':[2000,2000,2000,2000,2000], 'light':'breathing',
                'status':'queued', 'created_at':at, 'device_executed':False})
            self.activity({'source':'reminder','reply':'到时间了：'+item['title']})
            changed = True
        if changed: self.save()

    def activity(self, row):
        self.data["activity"].append({"at": now(), **row})
        self.data["activity"] = self.data["activity"][-40:]


class FocusSession:
    def __init__(self):
        self.id = uid("camera")
        self.last_seen = time.monotonic()
        self.away_since = self.last_at = None
        self.away_fired = False
        self.last_behavior = "none"
        self.behaviors = []

    def observe(self, decision, captured_at):
        at = datetime.fromisoformat(captured_at)
        if self.last_at and at <= self.last_at: return None
        if self.last_at and (at - self.last_at).total_seconds() > 8:
            self.away_since = None  # Missing frames are not evidence of continued absence.
        self.last_at = at
        if decision.away is True:
            if self.away_since is None: self.away_since = at
            if not self.away_fired and (at-self.away_since).total_seconds() >= 5:
                self.away_fired = True; return "离开工作电脑满5秒（演示规则）"
        else:
            self.away_since = None
            if decision.away is False: self.away_fired = False
        behavior = decision.behavior
        self.behaviors = [t for t in self.behaviors if at-t <= timedelta(minutes=10)]
        if behavior in {"phone", "fidget"} and behavior != self.last_behavior:
            self.behaviors.append(at)
        self.last_behavior = behavior
        if len(self.behaviors) >= 3:
            self.behaviors.clear(); return "10分钟内3次独立偏离行为"
        return None
