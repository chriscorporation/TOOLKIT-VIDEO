#!/usr/bin/env python3
"""m1-marks — renders the marks of a CLEAN TAKE in post (antialiased, editable, re-renderable without retakes).

usage: m1-marks <video> <timeline.jsonl> <out.mp4> --area X,Y,W,H [--color #188038] [--width 4] [--sync-video S]
  timeline.jsonl  written during the take by `MARK_LOG=<file> m1-mark play guion.txt` (+ `M1_CLICK_LOG` for clicks):
                  {"epoch":…, "cmd":"circle|box|highlight|arrow|spotlight|step|underline|ripple|sync", "args":[…], "env":{…}}
  --area          the screen area (points) the video was captured from (`m1-capture video --area X,Y,W,H`).
Alignment: the `sync` entry's white square is found in the video (first frame where it is white); every epoch is
mapped to video time from it (or pass --sync-video). Per-mark style from its env: MARK_COLOR, MARK_WIDTH, MARK_SECONDS,
HL_COLOR, HL_OPACITY. Motion (house recipe): draw-on 0.35 s ease-out, fade-out 0.2 s; ripple 24→64 pt in 0.35 s.
Frames are rendered with cairo (premultiplied ARGB) and un-premultiplied in numpy before piping straight BGRA to ffmpeg
(ffmpeg's unpremultiply / overlay alpha=premultiplied left translucent marks applied twice: 30 % green came out gray).
"""
import argparse, json, math, subprocess, sys
import cairo
import numpy as np

FF = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y']


def hexrgba(h, a=1.0):
    h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (a,)


def ease(p):
    p = max(0.0, min(1.0, p)); return 1 - (1 - p) ** 3


def probe(video):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate',
                          '-show_entries', 'format=duration', '-of', 'json', video], capture_output=True, text=True).stdout
    j = json.loads(out); s = j['streams'][0]; n, d = s['r_frame_rate'].split('/')
    return s['width'], s['height'], float(n) / float(d), float(j['format']['duration'])


def find_sync(video, px, py, fps):
    """First video time where the 32-pt sync square (top-left at px,py in pixels) is white."""
    p = subprocess.run(FF + ['-i', video, '-vf', f'crop=16:16:{int(px) + 8}:{int(py) + 8},format=gray', '-f', 'rawvideo', '-'],
                       capture_output=True)
    n = 256
    for i in range(len(p.stdout) // n):
        if sum(p.stdout[i * n:(i + 1) * n]) / n > 235:
            return i / fps
    raise SystemExit('no encontré el destello de sync en el video (¿quedó fuera del área?)')


class Mark:
    def __init__(self, e, t0, k, a):
        self.cmd, self.args, self.env, self.t0 = e['cmd'], [float(x) for x in e['args'] if _num(x)], e.get('env', {}), t0
        self.k, self.ax, self.ay = k, a[0], a[1]   # points → pixels scale and area origin
        self.dur = float(self.env.get('MARK_SECONDS', 0.42 if self.cmd == 'ripple' else 2.5))

    def P(self, x, y):
        return (x - self.ax) * self.k, (y - self.ay) * self.k


def _num(x):
    try:
        float(x); return True
    except ValueError:
        return False


def draw(ctx, m, t, color, width):
    lt = t - m.t0
    if lt < 0 or lt > m.dur:
        return
    col = m.env.get('MARK_COLOR', color); lw = float(m.env.get('MARK_WIDTH', width)) * m.k
    grow = ease(lt / 0.35); fade = 1.0 if lt < m.dur - 0.2 else max(0.0, (m.dur - lt) / 0.2)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND); ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    a = m.args
    if m.cmd == 'circle':
        cx, cy = m.P(a[0], a[1]); r = a[2] * m.k
        ctx.set_source_rgba(*hexrgba(col, fade)); ctx.set_line_width(lw)
        ctx.new_path(); ctx.arc(cx, cy, r, -math.pi / 2, -math.pi / 2 + 2 * math.pi * grow); ctx.stroke()
    elif m.cmd in ('box', 'bracket'):
        x, y = m.P(a[0], a[1]); w, h = a[2] * m.k, a[3] * m.k; rad = 10 * m.k
        ctx.set_source_rgba(*hexrgba(col, fade * grow)); ctx.set_line_width(lw)
        s = 0.96 + 0.04 * grow; cx, cy = x + w / 2, y + h / 2; ww, hh = w * s, h * s
        ctx.new_path(); _rrect(ctx, cx - ww / 2, cy - hh / 2, ww, hh, rad); ctx.stroke()
    elif m.cmd == 'highlight':
        x, y = m.P(a[0], a[1]); w, h = a[2] * m.k, a[3] * m.k
        hc = m.env.get('HL_COLOR', col); op = float(m.env.get('HL_OPACITY', 0.3))
        ctx.set_source_rgba(*hexrgba(hc, op * fade)); ctx.rectangle(x, y, w * ease(lt / 0.3), h); ctx.fill()
    elif m.cmd == 'underline':
        x, y = m.P(a[0], a[1]); w = a[2] * m.k
        ctx.set_source_rgba(*hexrgba(col, fade)); ctx.set_line_width(lw); ctx.move_to(x, y); ctx.line_to(x + w * grow, y); ctx.stroke()
    elif m.cmd == 'arrow':
        tx, ty = m.P(a[0], a[1]); fx, fy = m.P(a[2], a[3]) if len(a) >= 4 else (tx - 140 * m.k, ty + 90 * m.k)
        ex, ey = fx + (tx - fx) * grow, fy + (ty - fy) * grow
        ctx.set_source_rgba(*hexrgba(col, fade)); ctx.set_line_width(lw)
        ctx.move_to(fx, fy); ctx.line_to(ex, ey); ctx.stroke()
        if grow > 0.6:
            ang = math.atan2(ey - fy, ex - fx); L = 16 * m.k
            for s in (-1, 1):
                ctx.move_to(ex, ey); ctx.line_to(ex - L * math.cos(ang + s * 0.5), ey - L * math.sin(ang + s * 0.5))
            ctx.stroke()
    elif m.cmd in ('spotlight', 'spotlight-circle'):
        ctx.set_source_rgba(0, 0, 0, 0.55 * min(1, lt / 0.25) * fade)
        ctx.rectangle(0, 0, 1e5, 1e5)
        if m.cmd == 'spotlight':
            x, y = m.P(a[0], a[1]); _rrect(ctx, x, y, a[2] * m.k, a[3] * m.k, 12 * m.k)
        else:
            cx, cy = m.P(a[0], a[1]); ctx.new_sub_path(); ctx.arc(cx, cy, a[2] * m.k, 0, 2 * math.pi)
        ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD); ctx.fill(); ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
    elif m.cmd == 'step':
        cx, cy = m.P(a[0], a[1]); r = 18 * m.k * (0.6 + 0.4 * ease(lt / 0.25))
        ctx.set_source_rgba(*hexrgba(col, fade)); ctx.arc(cx, cy, r, 0, 2 * math.pi); ctx.fill()
        ctx.set_source_rgba(1, 1, 1, fade); ctx.select_font_face('Liberation Sans', 0, 1); ctx.set_font_size(20 * m.k)
        txt = str(int(a[2])) if len(a) > 2 else '1'; e = ctx.text_extents(txt)
        ctx.move_to(cx - e.width / 2 - e.x_bearing, cy - e.height / 2 - e.y_bearing); ctx.show_text(txt)
    elif m.cmd == 'ripple':
        cx, cy = m.P(a[0], a[1]); p = ease(lt / 0.35); r = (12 + 20 * p) * m.k
        ctx.set_source_rgba(*hexrgba(col, 0.6 * (1 - p))); ctx.set_line_width(3 * m.k)
        ctx.new_path(); ctx.arc(cx, cy, r, 0, 2 * math.pi); ctx.stroke()


def _rrect(ctx, x, y, w, h, r):
    ctx.new_sub_path(); ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0); ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi); ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2); ctx.close_path()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video'); ap.add_argument('timeline'); ap.add_argument('out')
    ap.add_argument('--area', required=True); ap.add_argument('--color', default='#188038'); ap.add_argument('--width', type=float, default=4)
    ap.add_argument('--sync-video', type=float)
    a = ap.parse_args()
    W, H, fps, dur = probe(a.video); ax, ay, aw, ah = map(float, a.area.split(',')); k = W / aw
    ev = [json.loads(l) for l in open(a.timeline) if l.strip()]
    sync = next((e for e in ev if e['cmd'] == 'sync'), None)
    if not sync:
        raise SystemExit('el timeline no tiene línea sync')
    sx, sy = float(sync['args'][0]), float(sync['args'][1])
    sv = a.sync_video if a.sync_video is not None else find_sync(a.video, (sx - ax) * k, (sy - ay) * k, fps)
    marks = [Mark(e, sv + (e['epoch'] - sync['epoch']), k, (ax, ay)) for e in ev if e['cmd'] != 'sync']
    print(f'sync en {sv:.3f} s · {len(marks)} marcas', file=sys.stderr)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); ctx = cairo.Context(surf); ctx.set_antialias(cairo.ANTIALIAS_BEST)
    enc = subprocess.Popen(FF + ['-i', a.video, '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}', '-r', str(fps), '-i', '-',
                                 '-filter_complex', '[0:v][1:v]overlay=0:0:format=rgb,format=yuv420p[v]', '-map', '[v]', '-map', '0:a?',
                                 '-c:v', 'libx264', '-crf', '14', '-preset', 'fast', '-c:a', 'copy', a.out], stdin=subprocess.PIPE)
    for i in range(int(dur * fps + 0.5)):
        t = i / fps
        ctx.set_operator(cairo.OPERATOR_CLEAR); ctx.paint(); ctx.set_operator(cairo.OPERATOR_OVER)
        for m in marks:
            draw(ctx, m, t, a.color, a.width)
        surf.flush(); px = np.frombuffer(surf.get_data(), np.uint8).reshape(H, surf.get_stride() // 4, 4)[:, :W].astype(np.uint16)
        al = px[..., 3:4]; rgb = np.where(al > 0, (px[..., :3] * 255 + al // 2) // np.maximum(al, 1), 0)
        enc.stdin.write(np.concatenate([np.minimum(rgb, 255), al], axis=2).astype(np.uint8).tobytes())
    enc.stdin.close(); enc.wait()
    print(a.out)


if __name__ == '__main__':
    main()
