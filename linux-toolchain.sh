#!/usr/bin/env bash
# Video toolchain for a bare Linux runner (WSL2 Ubuntu 26.04 on the HP, Debian 13 aarch64 on the Pi), mirroring the m5-videokit image
# (M5-PODTOOLS/Dockerfile, server flavor) so recipes behave the same as in the container. No VNC/noVNC/pm2:
# browser work (Grok) stays on the machines that hold the owner's profile.
# Usage: sudo PODTOOLS_SRC=/path/to/M5-PODTOOLS/src bash linux-toolchain.sh   (idempotent, re-run to resume)
set -uo pipefail
[ "$(id -u)" = 0 ] || { echo 'Corre con sudo'; exit 1; }
: "${PODTOOLS_SRC:?Define PODTOOLS_SRC con la carpeta src/ de M5-PODTOOLS}"
RUN_USER=${SUDO_USER:-chris}
WHISPER_CPP_VERSION=v1.9.5 BLENDER_VERSION=5.2.3 IMAGEMAGICK_VERSION=7.1.2-34 GIFSKI_VERSION=1.34.0
ARCH=$(uname -m)   # x86_64 or aarch64; what has no aarch64 build is skipped out loud, never faked
no_build() { echo "sin build para $ARCH: $1"; }
export DEBIAN_FRONTEND=noninteractive
echo "APT::Get::Lock::Timeout \"900\"; DPkg::Lock::Timeout \"900\";" > /etc/apt/apt.conf.d/90hvs-lock-wait   # waits instead of failing when another apt runs
failed=()
step() { local name=$1; shift; echo "== $name"; if "$@"; then echo "ok $name"; else echo "FALLA $name"; failed+=("$name"); fi; }

apt_base() {
  apt-get -o DPkg::Lock::Timeout=900 update -q && apt-get -o DPkg::Lock::Timeout=900 install -y -q --no-install-recommends \
    ca-certificates curl unzip xz-utils git bc sox libimage-exiftool-perl squashfs-tools \
    python3 python3-venv python3-dev build-essential cmake pkg-config libcairo2-dev libpango1.0-dev \
    fonts-liberation fonts-dejavu-core fonts-noto-color-emoji fonts-noto-core fonts-noto-cjk \
    fonts-inter fonts-montserrat fonts-bebas-neue fonts-league-spartan fonts-open-sans fonts-lato fonts-roboto \
    libgomp1 libgl1 libegl1 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libsm6 libxext6 \
    mediainfo rubberband-cli tesseract-ocr tesseract-ocr-spa potrace webp pngquant librsvg2-bin \
    ghostscript poppler-utils aria2 rclone ripgrep fd-find xvfb xauth espeak-ng \
    libvips-tools jpegoptim gifsicle frei0r-plugins uuid-runtime lsof xxd file tmux rsync \
    libvulkan1 vulkan-tools mesa-vulkan-drivers tigervnc-standalone-server tigervnc-tools websockify x11-utils xdotool openssh-server netcat-openbsd \
  && for p in gpac inkscape fontforge optipng qpdf p7zip-full perceptualdiff \
      bat eza sd yq gron htmlq miller xh hurl just glow hyperfine tokei git-delta difftastic procs du-dust duf entr watchexec lnav; do apt-get install -y -q --no-install-recommends $p || echo "opcional sin paquete: $p"; done \
  && { [ -x /usr/bin/batcat ] && ln -sf /usr/bin/batcat /usr/local/bin/bat; true; } \
  && ln -sf /usr/bin/fdfind /usr/local/bin/fd && fc-cache -f >/dev/null
}
ffmpeg_static() {  # same GPL build as the container: libass, loudnorm, vidstab, rubberband
  local build=linux64; [ "$ARCH" = aarch64 ] && build=linuxarm64
  mkdir -p /opt/ffmpeg && curl -fsSL "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-$build-gpl.tar.xz" \
    | tar -xJ --strip-components=2 -C /opt/ffmpeg --wildcards '*/bin/*' && /opt/ffmpeg/ffmpeg -hide_banner -version | head -1
}
imagemagick7() {
  command -v magick >/dev/null && magick -version | grep -q 'ImageMagick 7' && return 0
  [ "$ARCH" = x86_64 ] || { apt-get install -y -q --no-install-recommends imagemagick && magick -version | head -1; return; }   # the AppImage is x86_64 only
  curl -fsSL -o /tmp/magick.AppImage "https://github.com/ImageMagick/ImageMagick/releases/download/${IMAGEMAGICK_VERSION}/ImageMagick-${IMAGEMAGICK_VERSION}-gcc-x86_64.AppImage" || return 1
  local off; off=$(python3 -c "import struct,sys;f=open(sys.argv[1],'rb').read(64);o=struct.unpack_from('<Q',f,0x28)[0];s,n=struct.unpack_from('<HH',f,0x3A);print(o+s*n)" /tmp/magick.AppImage)
  rm -rf /opt/imagemagick && unsquashfs -q -o "$off" -d /opt/imagemagick /tmp/magick.AppImage && rm -f /tmp/magick.AppImage
  ln -sf /opt/imagemagick/AppRun /usr/local/bin/magick
  for c in convert montage identify mogrify composite; do printf '#!/bin/sh\nexec magick %s "$@"\n' "$c" > /usr/local/bin/$c; chmod +x /usr/local/bin/$c; done
  magick -version | head -1
}
gifski_bin() { [ "$ARCH" = x86_64 ] || { no_build gifski; return 0; }; curl -fsSL "https://github.com/ImageOptim/gifski/releases/download/${GIFSKI_VERSION}/gifski-${GIFSKI_VERSION}.tar.xz" | tar -xJ --strip-components=1 -C /usr/local/bin linux/gifski && chmod +x /usr/local/bin/gifski; }
small_bins() {
  curl -fsSL "https://github.com/oxipng/oxipng/releases/download/v10.2.1/oxipng-10.2.1-$ARCH-unknown-linux-musl.tar.gz" \
    | tar -xz --strip-components=1 -C /usr/local/bin "oxipng-10.2.1-$ARCH-unknown-linux-musl/oxipng" \
  && curl -fsSL "https://github.com/linebender/resvg/releases/download/v0.49.0/resvg-linux-$ARCH.tar.gz" | tar -xz -C /usr/local/bin resvg \
  || return 1
  [ "$ARCH" = x86_64 ] || { no_build c2patool; return 0; }
  curl -fsSL https://github.com/contentauth/c2pa-rs/releases/download/c2patool-v0.27.22/c2patool-v0.27.22-x86_64-unknown-linux-gnu.tar.gz | tar -xz -C /tmp \
  && install -m 755 "$(find /tmp -type f -name c2patool | head -1)" /usr/local/bin/c2patool
}
whisper_cpp() {
  command -v whisper-cli >/dev/null && return 0
  rm -rf /tmp/whisper.cpp && git clone -q --depth 1 -b "$WHISPER_CPP_VERSION" https://github.com/ggml-org/whisper.cpp /tmp/whisper.cpp \
  && cmake -S /tmp/whisper.cpp -B /tmp/whisper.cpp/build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=ON -DWHISPER_BUILD_TESTS=OFF >/dev/null \
  && cmake --build /tmp/whisper.cpp/build -j"$(nproc)" --target whisper-cli >/dev/null \
  && install -m 755 /tmp/whisper.cpp/build/bin/whisper-cli /usr/local/bin/whisper-cli && rm -rf /tmp/whisper.cpp
}
blender_bin() {
  [ -x /opt/blender/blender ] && return 0
  [ "$ARCH" = x86_64 ] || { no_build blender; return 0; }   # blender.org publishes no linux-arm64
  mkdir -p /opt/blender && curl -fsSL "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
    | tar -xJ --strip-components=1 -C /opt/blender && ln -sf /opt/blender/blender /usr/local/bin/blender
}
chrome_stable() {  # HyperFrames renders with its own headless shell; Chrome is for puppeteer/playwright scripts
  command -v google-chrome >/dev/null && return 0
  [ "$ARCH" = x86_64 ] || { apt-get install -y -q --no-install-recommends chromium && ln -sf /usr/bin/chromium /usr/local/bin/google-chrome; return; }   # no arm64 .deb; HyperFrames finds the system Chromium by itself
  curl -fsSL -o /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
  && apt-get install -y -q --no-install-recommends /tmp/chrome.deb && rm -f /tmp/chrome.deb
}
python_venv() {  # Python 3.12 like the container (Ubuntu 24.04); 26.04's system Python lacks wheels for some pins
  command -v uv >/dev/null || curl -fsSL https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
  [ -x /opt/venv/bin/python ] || UV_PYTHON_INSTALL_DIR=/opt/uv-python uv venv --python 3.12 /opt/venv || return 1
  local pip=(uv pip install --python /opt/venv/bin/python -q)
  local ae=(auto-editor==29.3.1); [ "$ARCH" = x86_64 ] || ae=()   # its wheel only downloads x86_64; arm64 gets the release binary below
  "${pip[@]}" av==18.1.0 faster-whisper==1.2.1 "${ae[@]}" manim==0.22.0 pillow numpy pycairo==1.29.2 \
      yt-dlp==2026.10.21 gallery-dl==1.32.18 instaloader==4.15.5 \
      pyloudnorm==0.2.0 librosa==1.0.0 pydub==0.25.1 soundfile==0.14.0 edge-tts==7.3.1 \
      scenedetect==0.7.2 opencv-python-headless==5.0.0.93 rembg==2.0.86 onnxruntime==1.31.0 \
      playwright==1.64.1 elevenlabs==2.74.1 anthropic==2.3.0 openai==3.37.0 uv \
      google-genai==2.33.0 google-auth==2.62.0 google-auth-oauthlib==1.5.0 google-api-python-client==2.201.0 \
      pysubs2==1.9.0 ffmpeg-normalize==1.43.0 ffmpeg-quality-metrics==3.13.0 \
      kokoro-onnx==0.6.1 piper-tts==1.8.0 ffsubsync==0.5.1 opentimelineio==0.18.1 pyvips==3.2.0 || return 1
  # On aarch64 diffq has no cp312 wheel and builds from source; if it cannot, the machine keeps working without vocal separation.
  "${pip[@]}" --extra-index-url https://download.pytorch.org/whl/cpu "audio-separator[cpu]==0.47.1" || { [ "$ARCH" = x86_64 ] && return 1; no_build audio-separator; }
  /opt/venv/bin/python -m pip --version >/dev/null 2>&1 || /opt/venv/bin/python -m ensurepip >/dev/null
  uv pip freeze --python /opt/venv/bin/python > /opt/versions-pip.txt
}
auto_editor_arm() {
  [ "$ARCH" = x86_64 ] && return 0
  curl -fsSL -o /usr/local/bin/auto-editor https://github.com/WyattBlue/auto-editor/releases/download/31.8.0/auto-editor-linux-aarch64 && chmod 755 /usr/local/bin/auto-editor && auto-editor --version
}
podtools() {  # same-name Linux equivalents of macOS-only commands: say, sips, mlx_whisper, m1-post/m1-vfx…
  rm -rf /opt/podtools.new && cp -r "$PODTOOLS_SRC" /opt/podtools.new && rm -rf /opt/podtools && mv /opt/podtools.new /opt/podtools
  rm -f /opt/podtools/bin/claude-swap   # account swap is the container's; never on a runner
  for r in "/home/$RUN_USER/.npm-global/bin/hyperframes" /usr/local/bin/hyperframes /opt/node/bin/hyperframes; do   # wherever THIS machine has HyperFrames
    [ -x "$r" ] && { sed -i "s#^REAL=.*#REAL=$r#" /opt/podtools/bin/hyperframes 2>/dev/null; break; }                # (image: /usr/local/bin; runner: ~/.npm-global)
  done
  cd /opt/podtools && chmod +x post vfx whisper-srt.py smoke say sips mlx_whisper m1-review-pack mac-compat 2>/dev/null
  for c in post vfx smoke say sips mlx_whisper m1-review-pack viewers; do ln -sf /opt/podtools/$c /usr/local/bin/$c; done
  ln -sf /opt/podtools/chrome-userscripts.mjs /usr/local/bin/chrome-userscripts
  ln -sf /opt/podtools/post /usr/local/bin/m1-post && ln -sf /opt/podtools/vfx /usr/local/bin/m1-vfx
  mkdir -p /Users && [ -e /Users/chris ] || ln -s "/home/$RUN_USER" /Users/chris   # skills hardcode /Users/chris like on the Mac
  [ -L /Users/chris ] || echo "AVISO: /Users/chris es una carpeta real, no el enlace a /home/$RUN_USER: las recetas no la van a resolver"
}
ncnn_bins() {  # Real-ESRGAN + RIFE (ncnn-vulkan; CPU Vulkan through mesa lavapipe on this machine)
  [ -x /opt/ncnn/rife/rife-ncnn-vulkan ] && return 0
  [ "$ARCH" = x86_64 ] || { no_build "Real-ESRGAN y RIFE ncnn"; return 0; }
  mkdir -p /opt/ncnn/realesrgan /tmp/ncnn \
  && curl -fsSL -o /tmp/ncnn/re.zip https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip \
  && unzip -qo /tmp/ncnn/re.zip -d /opt/ncnn/realesrgan && rm -f /opt/ncnn/realesrgan/input*.jpg /opt/ncnn/realesrgan/onepiece_demo.mp4 \
  && curl -fsSL -o /tmp/ncnn/rife.zip https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-ubuntu.zip \
  && unzip -qo /tmp/ncnn/rife.zip -d /tmp/ncnn && rm -rf /opt/ncnn/rife && mv /tmp/ncnn/rife-ncnn-vulkan-20221029-ubuntu /opt/ncnn/rife \
  && chmod +x /opt/ncnn/realesrgan/realesrgan-ncnn-vulkan /opt/ncnn/rife/rife-ncnn-vulkan && rm -rf /tmp/ncnn
}
node_clis() {  # same global CLIs as the container, in the user's npm prefix (worker PATH already has it)
  sudo -u "$RUN_USER" -i npm install -g -q @openai/codex@0.164.0 @google/gemini-cli@0.65.0 @playwright/mcp@0.0.83 @higgsfield/cli@1.2.2 pm2@7.1.1 @ast-grep/cli
}
playwright_browsers() {  # Chromium for Playwright (Python and the MCP); HyperFrames keeps its own headless shell
  mkdir -p /opt/ms-playwright && PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright /opt/venv/bin/playwright install --with-deps chromium </dev/null \
  && chmod -R a+rwX /opt/ms-playwright \
  && sudo -u "$RUN_USER" -i env PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright bash -c 'node "$(npm root -g)/@playwright/mcp/node_modules/playwright/cli.js" install chromium </dev/null' \
  && chmod -R a+rwX /opt/ms-playwright
}
profile_env() {  # login shells and the worker see the same PATH and limits as the container
  cat > /etc/profile.d/hvs-toolchain.sh <<'ENV'
export PATH=/opt/podtools/bin:/opt/ffmpeg:/opt/venv/bin:$PATH
export PODTOOLS_HOME=/opt/podtools HYPERFRAMES_WHISPER_PATH=/usr/local/bin/whisper-cli PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
export PATH=/opt/ncnn/realesrgan:/opt/ncnn/rife:$PATH
export MAGICK_MEMORY_LIMIT=1GiB MAGICK_MAP_LIMIT=2GiB MAGICK_DISK_LIMIT=32GiB MAGICK_AREA_LIMIT=256MP MAGICK_TIME_LIMIT=1800
export HYPERFRAMES_NO_TELEMETRY=1 HYPERFRAMES_NO_UPDATE_CHECK=1 HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1
export HF_RENDER_WORKERS=${HF_RENDER_WORKERS:-3}   # HP i7-4770T 2026-10-29: auto 30 s · 3 workers 16 s · 6 workers 17 s
ENV
}

step apt apt_base
step ffmpeg ffmpeg_static
step imagemagick imagemagick7
step gifski gifski_bin
step bins small_bins
step whisper whisper_cpp
step blender blender_bin
step chrome chrome_stable
step python python_venv
step auto-editor auto_editor_arm
step ncnn ncnn_bins
step node-clis node_clis
step playwright playwright_browsers
step podtools podtools
step profile profile_env
chown -R "$RUN_USER:$RUN_USER" /opt/venv 2>/dev/null
echo "FALLAS: ${failed[*]:-ninguna}"
[ ${#failed[@]} -eq 0 ]
