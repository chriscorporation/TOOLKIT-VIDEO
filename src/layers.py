#!/usr/bin/env python3
"""m1-layers — post-composited text layers for tutorials (crisp, drawn AFTER zoom/crop, never cut by it).

usage: m1-layers <in.mp4> <layers.txt> <out.mp4>
layers.txt, one element per line (seconds of THIS video; '#' comments):
  <t0> <t1> sub   "texto"                      subtitle pill (bottom-center, ~80 % height), wraps to 2 lines
  <t0> <t1> chip  "Paso 2/3 · Suma"            chapter chip, top-left
  <t0> <t1> keys  "⌘ B"                        keycaps (space-separated keys), centered above the subtitle
  <t0> <t1> title "Título" ["Subtítulo"]       centered title card over the live screen (no black cut)
  <t0> <t1> lower "Nombre" ["rol"]             lower third, bottom-left
Env: LAYER_ACCENT (#FF2D55), LAYER_FONT / LAYER_FONT_REG / LAYER_MONO (TTF paths), LAYER_SCALE (1.0),
     LAYER_SUB_Y (0.80) · LAYER_KEYS_Y (0.66) · LAYER_TITLE_X/Y (0.5/0.46) · LAYER_CHIP_X/Y (40/36 px at 1080p).
Each element fades and slides 14 px into place in 0.2 s and fades out in 0.15 s (one motion family, always eased).
"""
import os, shlex, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FF = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y']
HOME = os.path.expanduser('~')
FONT = os.environ.get('LAYER_FONT') or next((f for f in (f'{HOME}/Library/Fonts/google-fonts/ofl/googlesans/GoogleSansBold-Static.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/System/Library/Fonts/Avenir Next.ttc', '/System/Library/Fonts/HelveticaNeue.ttc') if os.path.exists(f)))
FONT_REG = os.environ.get('LAYER_FONT_REG') or FONT
MONO = os.environ.get('LAYER_MONO') or next((f for f in (f'{HOME}/Library/Fonts/JetBrainsMono[wght].ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
        '/System/Library/Fonts/Menlo.ttc') if os.path.exists(f)), FONT)
ACCENT = os.environ.get('LAYER_ACCENT', '#FF2D55')
SCALE = float(os.environ.get('LAYER_SCALE', '1'))
# Positions (fractions of the frame unless noted) so layers can sit in the frame's margins instead of over the app.
ENV = lambda k, d: float(os.environ.get(k, d))
SUB_Y, KEYS_Y = ENV('LAYER_SUB_Y', 0.80), ENV('LAYER_KEYS_Y', 0.66)
TITLE_X, TITLE_Y = ENV('LAYER_TITLE_X', 0.5), ENV('LAYER_TITLE_Y', 0.46)
CHIP_X, CHIP_Y = ENV('LAYER_CHIP_X', 40), ENV('LAYER_CHIP_Y', 36)     # px at 1080p scale


def font(path, size):
    try:
        f = ImageFont.truetype(path, size)
        if 'wght' in path:   # variable font: pick a bold instance when available
            try:
                f.set_variation_by_axes([700])
            except Exception:
                pass
        return f
    except OSError:
        return ImageFont.load_default(size)


def hexrgb(h, a=255):
    h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def shadowed(canvas, box, radius, fill, blur):
    """Rounded panel with a soft drop shadow (depth without a heavy outline)."""
    x0, y0, x1, y1 = box
    sh = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((x0, y0 + blur // 2, x1, y1 + blur // 2), radius, fill=(0, 0, 0, 110))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(canvas).rounded_rectangle(box, radius, fill=fill)


def wrap(draw, text, fnt, maxw):
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if draw.textlength(t, font=fnt) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    return lines + ([cur] if cur else [])


def render(kind, args, W, H):
    """Returns (RGBA image W×H, slide_px) for one element."""
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im); u = H / 1080 * SCALE
    if kind == 'sub':
        f = font(FONT, int(44 * u)); lines = wrap(d, args[0], f, W * 0.72)[:2]
        lh = int(58 * u); tw = max(d.textlength(l, font=f) for l in lines)
        bw, bh = tw + 56 * u, lh * len(lines) + 30 * u; cx, cy = W / 2, H * SUB_Y
        shadowed(im, (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2), int(18 * u), (12, 12, 16, 205), int(14 * u))
        for i, l in enumerate(lines):
            d.text((cx, cy - bh / 2 + 15 * u + i * lh + lh / 2), l, font=f, fill=(255, 255, 255, 255), anchor='mm')
    elif kind == 'chip':
        f = font(FONT, int(30 * u)); txt = args[0]; tw = d.textlength(txt, font=f)
        x0, y0 = CHIP_X * u, CHIP_Y * u; dot = 14 * u; bw, bh = tw + 34 * u + dot + 14 * u, 58 * u
        shadowed(im, (x0, y0, x0 + bw, y0 + bh), int(bh / 2), (255, 255, 255, 240), int(10 * u))
        d.ellipse((x0 + 20 * u, y0 + bh / 2 - dot / 2, x0 + 20 * u + dot, y0 + bh / 2 + dot / 2), fill=hexrgb(ACCENT))
        d.text((x0 + 20 * u + dot + 12 * u, y0 + bh / 2), txt, font=f, fill=(20, 20, 26, 255), anchor='lm')
    elif kind == 'keys':
        f = font(MONO, int(40 * u)); caps = args[0].split(); gap = 14 * u
        sizes = [(max(d.textlength(k, font=f) + 44 * u, 76 * u), 76 * u) for k in caps]
        total = sum(w for w, _ in sizes) + gap * (len(caps) - 1); x = W / 2 - total / 2; y = H * KEYS_Y
        for k, (w, h) in zip(caps, sizes):
            shadowed(im, (x, y, x + w, y + h), int(14 * u), (250, 250, 252, 245), int(8 * u))
            d.rounded_rectangle((x, y + h - 7 * u, x + w, y + h), int(14 * u), fill=(205, 205, 215, 255))
            d.text((x + w / 2, y + h / 2 - 3 * u), k, font=f, fill=(25, 25, 32, 255), anchor='mm'); x += w + gap
    elif kind == 'title':
        f1, f2 = font(FONT, int(76 * u)), font(FONT_REG, int(34 * u))
        tw = max(d.textlength(args[0], font=f1), d.textlength(args[1], font=f2) if len(args) > 1 else 0)
        bw, bh = tw + 120 * u, (170 if len(args) > 1 else 130) * u; cx, cy = W * TITLE_X, H * TITLE_Y
        shadowed(im, (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2), int(28 * u), (255, 255, 255, 245), int(24 * u))
        d.rounded_rectangle((cx - bw / 2, cy - bh / 2, cx - bw / 2 + 12 * u, cy + bh / 2), int(6 * u), fill=hexrgb(ACCENT))
        d.text((cx, cy - (22 * u if len(args) > 1 else 0)), args[0], font=f1, fill=(18, 18, 24, 255), anchor='mm')
        if len(args) > 1:
            d.text((cx, cy + 46 * u), args[1], font=f2, fill=(90, 90, 104, 255), anchor='mm')
    elif kind == 'lower':
        f1, f2 = font(FONT, int(40 * u)), font(FONT_REG, int(28 * u)); x0, y1 = 60 * u, H * 0.88
        tw = max(d.textlength(args[0], font=f1), d.textlength(args[1], font=f2) if len(args) > 1 else 0); bh = (104 if len(args) > 1 else 70) * u
        shadowed(im, (x0, y1 - bh, x0 + tw + 64 * u, y1), int(16 * u), (255, 255, 255, 240), int(12 * u))
        d.rounded_rectangle((x0, y1 - bh, x0 + 10 * u, y1), int(5 * u), fill=hexrgb(ACCENT))
        d.text((x0 + 34 * u, y1 - bh + 18 * u), args[0], font=f1, fill=(18, 18, 24, 255), anchor='lt')
        if len(args) > 1:
            d.text((x0 + 34 * u, y1 - 18 * u), args[1], font=f2, fill=(90, 90, 104, 255), anchor='lb')
    else:
        raise SystemExit(f'tipo desconocido: {kind}')
    return im, int(14 * u)


def main():
    src, spec, out = sys.argv[1:4]
    W, H, R = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate',
                              '-of', 'csv=p=0', src], capture_output=True, text=True).stdout.strip().split(',')
    W, H = int(W), int(H); tmp = tempfile.mkdtemp(prefix='m1layers'); els = []
    for n, line in enumerate(open(spec, encoding='utf-8')):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        p = shlex.split(line); t0, t1, kind, args = float(p[0]), float(p[1]), p[2], p[3:]
        im, slide = render(kind, args, W, H); f = os.path.join(tmp, f'{n:03d}.png'); im.save(f); els.append((t0, t1, f, slide))
    if not els:
        raise SystemExit('sin elementos')
    inputs, chain, last = ['-i', src], '', '0:v'
    for i, (t0, t1, f, slide) in enumerate(els, 1):
        inputs += ['-loop', '1', '-framerate', R, '-t', f'{t1 + 0.1:.2f}', '-i', f]
        chain += (f'[{i}:v]format=rgba,fade=t=in:st={t0}:d=0.2:alpha=1,fade=t=out:st={max(t0, t1 - 0.15)}:d=0.15:alpha=1[l{i}];'
                  f"[{last}][l{i}]overlay=x=0:y='{slide}*(1-min(1,max(0,(t-{t0})/0.2)))^2':eof_action=pass:"
                  f"enable='between(t,{t0},{t1})'[v{i}];")
        last = f'v{i}'
    subprocess.run(FF + inputs + ['-filter_complex', chain.rstrip(';'), '-map', f'[{last}]', '-map', '0:a?', '-c:v', 'libx264',
                                  '-crf', '16', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-c:a', 'copy', out], check=True)
    print(out)


if __name__ == '__main__':
    main()
