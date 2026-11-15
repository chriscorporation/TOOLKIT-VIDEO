#!/usr/bin/env python3
"""m1-frame — "window on a background" framing (Screen Studio look) for a screen recording.

usage: m1-frame <in.mp4> <out.mp4> [--size 1920x1080] [--pad 80] [--radius 22] [--bg "#1E1B4B,#7C3AED" | --bg image.png]
The recording is scaled to fit inside the frame minus the padding (keeping its aspect), its corners rounded, a soft
drop shadow added, and it is centered on a diagonal gradient (two hex colors) or an image. Audio is copied.
"""
import argparse, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFilter

FF = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y']


def gradient(W, H, c0, c1):
    a = tuple(int(c0.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)); b = tuple(int(c1.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
    small = Image.new('RGB', (64, 36))
    for y in range(36):
        for x in range(64):
            t = (x / 63 * 0.6 + y / 35 * 0.4)
            small.putpixel((x, y), tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3)))
    return small.resize((W, H), Image.BICUBIC)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('out'); ap.add_argument('--size', default='1920x1080')
    ap.add_argument('--pad', type=int, default=80); ap.add_argument('--radius', type=int, default=22)
    ap.add_argument('--pad-top', type=int, help='top margin (room for a chapter chip above the window)')
    ap.add_argument('--bg', default='#1E1B4B,#7C3AED'); ap.add_argument('--shadow', type=int, default=40)
    a = ap.parse_args()
    W, H = map(int, a.size.split('x'))
    vw, vh = map(int, subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                                      '-of', 'csv=p=0:s=x', a.src], capture_output=True, text=True).stdout.strip().split('x'))
    top = a.pad_top if a.pad_top is not None else a.pad
    s = min((W - 2 * a.pad) / vw, (H - top - a.pad) / vh); fw, fh = int(vw * s) // 2 * 2, int(vh * s) // 2 * 2
    x, y = (W - fw) // 2, top + (H - top - a.pad - fh) // 2
    tmp = tempfile.mkdtemp(prefix='m1frame')
    bg = Image.open(a.bg).convert('RGB').resize((W, H)) if os.path.exists(a.bg) else gradient(W, H, *a.bg.split(','))
    sh = Image.new('L', (W, H), 0); ImageDraw.Draw(sh).rounded_rectangle((x, y + a.shadow // 2, x + fw, y + fh + a.shadow // 2), a.radius, fill=150)
    sh = sh.filter(ImageFilter.GaussianBlur(a.shadow)); bg.paste((0, 0, 0), (0, 0), sh); bg.save(f'{tmp}/bg.png')
    mask = Image.new('L', (fw, fh), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, fw - 1, fh - 1), a.radius, fill=255); mask.save(f'{tmp}/mask.png')
    fc = (f'[0:v]scale={fw}:{fh}:flags=lanczos,format=rgba[v];[2:v]format=gray[m];[v][m]alphamerge[r];'
          f'[1:v][r]overlay={x}:{y}:shortest=1,format=yuv420p[o]')
    dur = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', a.src],
                         capture_output=True, text=True).stdout.strip()
    fps = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate', '-of', 'csv=p=0', a.src],
                         capture_output=True, text=True).stdout.strip() or '30'
    # Looped stills need an explicit length (or the graph never ends) and the source frame rate (the background is the
    # overlay's main input, so its default 25 fps became the output rate).
    subprocess.run(FF + ['-i', a.src, '-loop', '1', '-framerate', fps, '-t', dur, '-i', f'{tmp}/bg.png',
                         '-loop', '1', '-framerate', fps, '-t', dur, '-i', f'{tmp}/mask.png',
                         '-filter_complex', fc, '-map', '[o]', '-map', '0:a?', '-c:v', 'libx264', '-crf', '16', '-preset', 'medium',
                         '-c:a', 'copy', a.out], check=True)
    print(a.out)


if __name__ == '__main__':
    main()
