# TOOLKIT-VIDEO — video editing/rendering toolkit on top of the RunPod ComfyUI image (GPU NVIDIA, amd64).
# Adds: ffmpeg (BtbN GPL, NVENC), HyperFrames, Node 24, ImageMagick 7, Blender, whisper.cpp, sox, Real-ESRGAN/RIFE (ncnn),
# Python 3.12 venv (faster-whisper, rembg, auto-editor, manim, yt-dlp…) and Linux shims of macOS commands (say, sips, mlx_whisper).
# No credentials are baked in: every API key is read from the environment at run time.
ARG BASE=runpod/comfyui:2.2.0-comfyuiv0.44.0-cuda12.8
FROM ${BASE}
ARG NODE_V=24.22.3
ARG HYPERFRAMES_V=0.9.37
ENV DEBIAN_FRONTEND=noninteractive
COPY linux-toolchain.sh /tmp/toolkit/linux-toolchain.sh
COPY src /tmp/toolkit/src
RUN apt-get update -q && apt-get install -y -q --no-install-recommends sudo xz-utils curl ca-certificates \
 && curl -fsSL https://nodejs.org/dist/v${NODE_V}/node-v${NODE_V}-linux-x64.tar.xz | tar -xJ -C /opt \
 && mv /opt/node-v${NODE_V}-linux-x64 /opt/node \
 && for b in node npm npx; do ln -sf /opt/node/bin/$b /usr/local/bin/$b; done \
 && npm config set prefix /usr/local && npm install -g -q hyperframes@${HYPERFRAMES_V}
# the farm installer reports each step; optional extras may fail without breaking the image, the smoke test below decides
RUN SUDO_USER=root PODTOOLS_SRC=/tmp/toolkit/src bash /tmp/toolkit/linux-toolchain.sh || true \
 && hyperframes browser ensure \
 && rm -rf /var/lib/apt/lists/* /tmp/toolkit /root/.cache/pip /root/.cache/uv /root/.npm
RUN bash -lc 'set -e; ffmpeg -hide_banner -encoders | grep -q h264_nvenc; hyperframes --version; magick -version | head -1; \
  blender --version | head -1; whisper-cli --help >/dev/null 2>&1 || whisper-cli -h >/dev/null; sox --version; \
  /opt/venv/bin/python -c "import faster_whisper, rembg, av; print(\"venv ok\")"'
LABEL org.opencontainers.image.source="https://github.com/chriscorporation/TOOLKIT-VIDEO" \
      org.opencontainers.image.description="Internal utility to center caption text" \
      org.opencontainers.image.licenses="MIT"
