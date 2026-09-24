import platform
import subprocess
from dataclasses import dataclass


@dataclass
class AppContext:
    app: str = ""
    title: str = ""
    available: bool = False
    reason: str = ""


class MacContextMonitor:
    """Reads only the frontmost app name and window title on macOS."""

    def read(self):
        if platform.system() != "Darwin":
            return AppContext(available=False, reason="not_macos")

        script = '''
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
end tell
tell application "System Events"
    tell process frontApp
        try
            set winTitle to name of front window
        on error
            set winTitle to ""
        end try
    end tell
end tell
return frontApp & "|||MINDLOOP|||" & winTitle
'''
        try:
            out = subprocess.check_output(
                ["osascript", "-e", script],
                text=True,
                timeout=2,
                stderr=subprocess.DEVNULL,
            ).strip()
            parts = out.split("|||MINDLOOP|||", 1)
            return AppContext(
                app=parts[0].strip() if parts else "",
                title=parts[1].strip() if len(parts) > 1 else "",
                available=True,
            )
        except Exception as e:
            return AppContext(
                available=False,
                reason=f"context_unavailable:{type(e).__name__}",
            )


class DriftDetector:
    """V0 heuristic: checks whether digital context conflicts with declared task."""

    def score(self, goal, ctx):
        if not ctx.available:
            return {"score": 0.0, "drift": False, "reason": "context_unavailable"}

        g = goal.lower()
        app = (ctx.app or "").lower()
        title = (ctx.title or "").lower()
        combined = f"{app} {title}"

        distraction_terms = [
            "youtube", "bilibili", "哔哩哔哩", "douyin", "抖音",
            "xiaohongshu", "小红书", "instagram", "twitter", "x.com",
        ]
        if any(x in combined for x in distraction_terms):
            return {"score": 0.92, "drift": True, "reason": "distracting_context"}

        if any(k in g for k in ["ppt", "汇报", "演示"]):
            expected = ["powerpoint", "keynote", "ppt"]
        elif any(k in g for k in ["论文", "paper", "overleaf", "文章"]):
            expected = ["chrome", "safari", "overleaf", "word", "preview", "tex"]
        elif any(k in g for k in ["代码", "程序", "coding", "项目"]):
            expected = ["visual studio code", "code", "terminal", "iterm", "xcode", "pycharm"]
        else:
            expected = []

        if expected and any(x in combined for x in expected):
            return {"score": 0.08, "drift": False, "reason": "context_matches_goal"}

        return {"score": 0.35, "drift": False, "reason": "uncertain_context"}
