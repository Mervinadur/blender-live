# Ready-made render machine for render-remote.sh: Blender (same version as the phone) + its libraries,
# SSH and ffmpeg, so a RunPod pod can start rendering as soon as it boots (no apt/download per job).
# Built and pushed by .github/workflows/pod-image.yml to ghcr.io/mervinadur/blender-pod:<version>.
FROM ubuntu:24.04
ARG BLENDER_VERSION=4.3.2
ENV DEBIAN_FRONTEND=noninteractive \
    NVIDIA_DRIVER_CAPABILITIES=all \
    NVIDIA_VISIBLE_DEVICES=all
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-server ca-certificates curl xz-utils ffmpeg \
      libx11-6 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxext6 libxkbcommon0 libxkbcommon-x11-0 \
      libsm6 libice6 libgl1 libegl1 libglx0 libwayland-client0 libwayland-cursor0 libwayland-egl1 \
      libdecor-0-0 libxcursor1 libxinerama1 libxrandr2 \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /run/sshd /root/.ssh /root/job
RUN mkdir -p /opt/blender \
 && curl -fsSL "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
    | tar -xJ -C /opt/blender --strip-components=1 \
 && /opt/blender/blender -b --version | head -1
COPY start.sh /start.sh
RUN chmod +x /start.sh
CMD ["/start.sh"]
