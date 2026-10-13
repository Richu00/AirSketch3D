import os, platform, subprocess, time, webbrowser
from pathlib import Path
try:
    import pyautogui
except Exception:  # headless environment (CI / tests) - no display available
    pyautogui = None

class ActionController:
    def __init__(self, config):
        self.config=config; self.last_cursor=None; self.dragging=False
        self.screen=pyautogui.size() if pyautogui else (1920,1080)
        if pyautogui: pyautogui.PAUSE=0.01; pyautogui.FAILSAFE=False
    def move_cursor(self,x,y,sensitivity=1.0,smoothing=0.7,invert_x=False,invert_y=False):
        sx,sy=self.screen; tx=max(0,min(sx-1,int(x*sx))); ty=max(0,min(sy-1,int(y*sy)))
        if invert_x: tx=sx-tx
        if invert_y: ty=sy-ty
        if self.last_cursor is None: nx,ny=tx,ty
        else: nx=int(self.last_cursor[0]*smoothing+tx*(1-smoothing)); ny=int(self.last_cursor[1]*smoothing+ty*(1-smoothing))
        self.last_cursor=(nx,ny)
        if pyautogui: pyautogui.moveTo(nx,ny,duration=0)
    def click(self):
        if pyautogui: pyautogui.click()
    def begin_drag(self):
        if not self.dragging:
            if pyautogui: pyautogui.mouseDown()
            self.dragging=True
    def end_drag(self):
        if self.dragging:
            if pyautogui: pyautogui.mouseUp()
            self.dragging=False
    def scroll(self,amount):
        if pyautogui: pyautogui.scroll(int(max(-8,min(8,-amount*10))))
    def browser_back(self):
        if pyautogui: pyautogui.hotkey(*(('command','[') if platform.system()=='Darwin' else ('alt','left')))
    def browser_forward(self):
        if pyautogui: pyautogui.hotkey(*(('command',']') if platform.system()=='Darwin' else ('alt','right')))
    def media(self,action,presses=1):
        keys={'next':'nexttrack','previous':'prevtrack','play_pause':'playpause','volume_up':'volumeup','volume_down':'volumedown'}
        if action in keys and pyautogui: pyautogui.press(keys[action],presses=max(1,int(presses)))
    def screenshot(self):
        out=Path.home()/"Pictures"/"AIRCONTROL"; out.mkdir(parents=True,exist_ok=True); path=out/f"aircontrol_{int(time.time())}.png"
        if pyautogui: pyautogui.screenshot(str(path))
        return str(path)
    def launch_app(self,name):
        for app in self.config.applications().get('applications',[]):
            if app['name'].lower()==name.lower():
                if platform.system()=='Darwin' and app.get('mac'):   # e.g. "open -a Calculator"
                    subprocess.Popen(app['mac'],shell=True); return True,f"Launched {name}"
                path=os.path.expandvars(app['path'])
                if Path(path).exists() or not Path(path).suffix or path.lower().endswith(('.exe','.bat')):
                    subprocess.Popen(path,shell=True); return True,f"Launched {name}"
                return False,f"Application not found: {path}"
        return False,f"Unknown application: {name}"
    def open_website(self,url): return webbrowser.open(url)
