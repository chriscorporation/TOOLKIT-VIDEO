# TOOLKIT-VIDEO — architecture

Public Docker image = RunPod ComfyUI base + the video toolchain of the render farm (`linux-toolchain.sh`, unchanged copy) + the
`src/` editing helpers. Built and pushed by GitHub Actions to GHCR; consumed by GPU pods that edit/render (HyperFrames, ffmpeg).

| Layer | Choice |
|---|---|
| Base | `runpod/comfyui:2.2.0-comfyuiv0.44.0-cuda12.8` |
| Runtime | Node 24.22.3, HyperFrames 0.9.37, Python 3.12 venv |
| Build | GitHub Actions, buildx, free-disk-space |
| Registry | `ghcr.io/chriscorporation/toolkit-video` (public) |

- [x] Kit reviewed for keys and personal data
- [ ] First CI build green
- [ ] Pod boots from the image and renders a HyperFrames project
- [ ] Sync `linux-toolchain.sh` when the farm's copy changes
