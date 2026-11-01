#!/usr/bin/env python3
"""Per-key LED control panel for the Ducky One 2 RGB (04d9:0348).

Protocol from javitonino/duckylights (GPL-2.0). No dependencies beyond Tk.
"""
import colorsys
import glob
import json
import os
import select
import sys
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox

VID, PID, IFACE = '04d9', '0348', 'input1'
ROWS, COLS = 6, 22
PAL_W, PAL_H = 480, 48
PROFILE_DIR = os.path.expanduser('~/.config/ducky-lights')
ACTIVE = os.path.join(PROFILE_DIR, 'active.json')  # applied at login by the service

# Inferred from the duckylights ES layout; colour index is col * ROWS + row.
LAYOUT = """
  ESC          F1    F2    F3    F4          F5    F6    F7    F8    F9   F10   F11   F12  PRTSC SCRLK PAUSE  CALC  MUTE  VOL-  VOL+
   `     1     2     3     4     5     6     7     8     9     0     -     =          BACK  INS   HOME PAGUP NUMLK  NUM/  NUM*  NUM-
  TAB    Q     W     E     R     T     Y     U     I     O     P     [     ]         ENTER  DEL   END  PAGDN  NUM7  NUM8  NUM9  NUM+
  CAPS   A     S     D     F     G     H     J     K     L     ;     '     #                                  NUM4  NUM5  NUM6
  LSH    <     Z     X     C     V     B     N     M     ,     .     /          RTSH               UP         NUM1  NUM2  NUM3
 LCTRL LMETA  LALT                   SPACE                   RALT        RMETA   FN  RCTRL  LEFT  DOWN RIGHT  NUM0        NUM. NENTR
""".strip('\n').split('\n')


def parse_layout():
    keys = {}
    for r, line in enumerate(LAYOUT):
        for c in range(COLS):
            t = line[c * 6:(c + 1) * 6].strip()
            if t:
                keys[(r, c)] = t
    # The layout above is the ISO one from duckylights; fix up for ANSI
    # (verified on hardware: (3,14) lights Enter, (2,14) lights \\|).
    keys[(2, 14)] = '\\'
    keys[(3, 14)] = 'ENTER'
    keys.pop((3, 12), None)
    keys.pop((4, 1), None)
    return keys


class Keyboard:
    def __init__(self):
        self.path = self.find()
        self.fd = os.open(self.path, os.O_RDWR)
        self.programming = False

    @staticmethod
    def find():
        for d in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
            uevent = open(os.path.join(d, 'device/uevent')).read().lower()
            if f'hid_id=0003:0000{VID}:0000{PID}' in uevent:
                phys = [l for l in uevent.splitlines() if l.startswith('hid_phys')]
                if phys and phys[0].endswith(IFACE):
                    return '/dev/' + os.path.basename(d)
        raise FileNotFoundError('Ducky keyboard (04d9:0348) not found')

    def _write(self, hexmsg):
        data = bytes.fromhex(hexmsg).ljust(64, b'\0')
        os.write(self.fd, data)
        if select.select([self.fd], [], [], 0.5)[0]:
            os.read(self.fd, 256)

    def apply(self, colors):
        """colors: list of ROWS*COLS 'rrggbb' strings, index = col*ROWS+row."""
        prefix = '01000000800100c100000000ffffffff00000000'
        data = prefix + ''.join(colors)
        # Leaving programming mode (4100) reverts the lights, so stay in it
        # until close().
        if not self.programming:
            self._write('4101')
            self.programming = True
        self._write('568100000100000008000000aaaaaaaa')
        for p in range(8):
            self._write('56830%d00' % p + data[p * 120:(p + 1) * 120])
        self._write('51280000ff')

    def close(self, leave_lights=False):
        """leave_lights: skip 4100 so the last frame stays (used when a
        background service owns the lighting)."""
        try:
            if self.programming and not leave_lights:
                self._write('4100')
        finally:
            os.close(self.fd)


def frame(colors):
    """Black out cells that have no key so nothing sticks at a stale colour."""
    out = ['000000'] * (ROWS * COLS)
    for (r, c) in parse_layout():
        out[c * ROWS + r] = colors[c * ROWS + r]
    return out


def load_colors(path):
    cols = json.load(open(path))
    assert len(cols) == ROWS * COLS
    return cols


def daemon():
    """Hold the saved startup pattern on the keyboard; follow edits and replugs."""
    import time
    kb, mtime, last = None, None, 0
    while True:
        try:
            m = os.path.getmtime(ACTIVE) if os.path.exists(ACTIVE) else None
            if kb is None:
                kb = Keyboard()
                mtime = None
            if m and (m != mtime or time.time() - last > 15):
                kb.apply(frame(load_colors(ACTIVE)))
                mtime, last = m, time.time()
        except (OSError, ValueError, AssertionError) as e:
            print('ducky-lights:', e, file=sys.stderr, flush=True)
            if kb:
                try:
                    os.close(kb.fd)
                except OSError:
                    pass
            kb = None
        time.sleep(2)


def hexcol(rgb):
    return '%02x%02x%02x' % tuple(int(round(x * 255)) for x in rgb)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Ducky Lights')
        self.configure(bg='#1e1e2e')
        self.keys = parse_layout()
        self.colors = ['ffffff'] * (ROWS * COLS)
        self.brush = tk.StringVar(value='ff0000')
        self.live = tk.BooleanVar(value=True)
        self.status = tk.StringVar()
        self.kb = None
        self.rects = {}
        self.connect()
        self.build()
        os.makedirs(PROFILE_DIR, exist_ok=True)

    def connect(self):
        try:
            self.kb = Keyboard()
            self.status.set(f'Connected: {self.kb.path}')
        except (FileNotFoundError, PermissionError) as e:
            self.kb = None
            hint = ' - run ./install.sh once' if isinstance(e, PermissionError) else ''
            self.status.set(f'Not connected: {e}{hint}')

    def build(self):
        cv = tk.Canvas(self, width=COLS * 34 + 20, height=ROWS * 34 + 20,
                       bg='#1e1e2e', highlightthickness=0)
        cv.pack(padx=10, pady=10, fill='both', expand=True)
        self.cv = cv
        cv.bind('<Configure>', lambda e: self.draw())
        cv.bind('<Button-1>', self.paint)
        cv.bind('<B1-Motion>', self.paint)
        cv.bind('<Button-3>', self.pick)

        pal = tk.Frame(self, bg='#1e1e2e')
        pal.pack(fill='x', padx=10, pady=(0, 6))
        self.pal_img = self.make_palette(PAL_W, PAL_H)
        self.pal = tk.Canvas(pal, width=PAL_W, height=PAL_H, highlightthickness=0,
                             cursor='crosshair')
        self.pal.create_image(0, 0, image=self.pal_img, anchor='nw')
        self.pal.pack(side='left')
        for ev in ('<Button-1>', '<B1-Motion>', '<Button-3>', '<B3-Motion>'):
            self.pal.bind(ev, self.pick_palette)
        tk.Label(pal, text='Click or right-click the rainbow to select a colour,\n'
                 'then paint keys with it', bg='#1e1e2e', fg='#aaa',
                 justify='left').pack(side='left', padx=12)

        bar = tk.Frame(self, bg='#1e1e2e')
        bar.pack(fill='x', padx=10)
        self.swatch = tk.Button(bar, width=4, bg='#' + self.brush.get(), command=self.choose)
        self.swatch.pack(side='left', padx=2)
        for text, fn in [('Fill all', self.fill_all), ('Rainbow →', self.rainbow),
                         ('Gradient ↓', self.gradient), ('Off', self.off),
                         ('Save…', self.save), ('Load…', self.load),
                         ('Set as startup', self.set_startup)]:
            tk.Button(bar, text=text, command=fn).pack(side='left', padx=2)
        tk.Checkbutton(bar, text='Live', variable=self.live, bg='#1e1e2e', fg='#ccc',
                       selectcolor='#333', command=self.maybe_apply).pack(side='left', padx=8)
        tk.Button(bar, text='Apply', command=self.apply).pack(side='left', padx=2)
        tk.Button(bar, text='Reconnect', command=self.reconnect).pack(side='right')
        tk.Label(self, textvariable=self.status, bg='#1e1e2e', fg='#aaa',
                 anchor='w').pack(fill='x', padx=12, pady=(6, 2))
        tk.Label(self, text='Click/drag to paint · right-click picks a key\'s colour',
                 bg='#1e1e2e', fg='#666', anchor='w').pack(fill='x', padx=12, pady=(0, 8))

    # -- helpers
    def draw(self):
        cv = self.cv
        w, h = max(cv.winfo_width(), 100), max(cv.winfo_height(), 50)
        self.U = U = max(min((w - 20) / COLS, (h - 20) / ROWS), 10)
        self.ox = (w - COLS * U) / 2
        self.oy = (h - ROWS * U) / 2
        cv.delete('all')
        self.rects = {}
        gap = max(U * 0.08, 2)
        for (r, c), label in self.keys.items():
            x, y = self.ox + c * U, self.oy + r * U
            self.rects[(r, c)] = cv.create_rectangle(
                x, y, x + U - gap, y + U - gap, outline='#555',
                fill='#' + self.colors[c * ROWS + r])
            cv.create_text(x + (U - gap) / 2, y + (U - gap) / 2, text=label[:5],
                           font=('sans', max(int(U / 4.5), 6)), fill='#888')

    def key_at(self, ev):
        U = self.U
        c, r = int((ev.x - self.ox) // U), int((ev.y - self.oy) // U)
        return (r, c) if (r, c) in self.keys else None

    def set_key(self, r, c, col):
        self.colors[c * ROWS + r] = col
        self.cv.itemconfig(self.rects[(r, c)], fill='#' + col)

    def set_all(self, fn):
        for (r, c) in self.keys:
            self.set_key(r, c, fn(r, c))
        self.maybe_apply()

    def paint(self, ev):
        k = self.key_at(ev)
        if k:
            self.set_key(*k, self.brush.get())
            self.maybe_apply(debounce=True)

    def pick(self, ev):
        k = self.key_at(ev)
        if k:
            self.set_brush(self.colors[k[1] * ROWS + k[0]])

    @staticmethod
    def make_palette(w, h):
        """Hue across, white -> pure -> black down, grey ramp on the right."""
        img = tk.PhotoImage(width=w, height=h)
        grey_w = 30
        hue_w = w - grey_w
        for y in range(h):
            t = y / (h - 1)
            row = []
            for x in range(hue_w):
                s, v = (0.1 + t * 1.8, 1.0) if t < 0.5 else (1.0, 2 - 2 * t)
                row.append('#' + hexcol(colorsys.hsv_to_rgb(x / hue_w, min(s, 1.0), v)))
            row += ['#' + hexcol((1 - t,) * 3)] * grey_w
            img.put('{' + ' '.join(row) + '}', to=(0, y))
        return img

    def pick_palette(self, ev):
        x = min(max(ev.x, 0), PAL_W - 1)
        y = min(max(ev.y, 0), PAL_H - 1)
        r, g, b = self.pal_img.get(x, y)[:3]
        self.set_brush('%02x%02x%02x' % (r, g, b))

    def set_brush(self, col):
        self.brush.set(col)
        self.swatch.configure(bg='#' + col)

    def choose(self):
        rgb, hx = colorchooser.askcolor(color='#' + self.brush.get(), parent=self)
        if hx:
            self.set_brush(hx[1:])

    # -- actions
    def fill_all(self): self.set_all(lambda r, c: self.brush.get())
    def off(self): self.set_all(lambda r, c: '000000')
    def rainbow(self): self.set_all(lambda r, c: hexcol(colorsys.hsv_to_rgb(c / COLS, 1, 1)))
    def gradient(self):
        self.set_all(lambda r, c: hexcol(colorsys.hsv_to_rgb(r / ROWS * 0.8, 1, 1)))

    _after = None
    def maybe_apply(self, debounce=False):
        if not self.live.get():
            return
        if debounce:
            if self._after:
                self.after_cancel(self._after)
            self._after = self.after(60, self.apply)
        else:
            self.apply()

    def apply(self):
        self._after = None
        if not self.kb:
            return
        try:
            self.kb.apply(frame(self.colors))
            self.status.set(f'Applied to {self.kb.path}')
        except OSError as e:
            self.status.set(f'Write failed: {e} (try Reconnect)')

    def set_startup(self):
        json.dump(self.colors, open(ACTIVE, 'w'))
        self.status.set('Saved as startup pattern (applied at login by the service)')

    def reconnect(self):
        if self.kb:
            self.kb.close()
        self.connect()
        self.apply()

    def save(self):
        f = filedialog.asksaveasfilename(initialdir=PROFILE_DIR, defaultextension='.json', parent=self)
        if f:
            json.dump(self.colors, open(f, 'w'))

    def load(self):
        f = filedialog.askopenfilename(initialdir=PROFILE_DIR, parent=self)
        if f:
            try:
                cols = json.load(open(f))
                assert len(cols) == ROWS * COLS
            except Exception as e:
                messagebox.showerror('Load failed', str(e), parent=self)
                return
            self.colors = cols
            for (r, c) in self.keys:
                self.set_key(r, c, cols[c * ROWS + r])
            self.maybe_apply()


def main():
    app = App()
    app.apply()

    def quit_():
        if app.kb:
            # If a startup pattern exists the service keeps the lights; don't
            # leave programming mode, which would revert them.
            if os.path.exists(ACTIVE):
                try:
                    app.kb.apply(frame(load_colors(ACTIVE)))
                except (OSError, ValueError, AssertionError):
                    pass
            app.kb.close(leave_lights=os.path.exists(ACTIVE))
        app.destroy()
    app.protocol('WM_DELETE_WINDOW', quit_)
    app.mainloop()


if __name__ == '__main__':
    if '--daemon' in sys.argv:
        daemon()
    if '--self-test' in sys.argv:
        k = parse_layout()
        print(len(k), 'keys;', sorted({c for _, c in k})[-1] + 1, 'cols')
        sys.exit()
    main()
