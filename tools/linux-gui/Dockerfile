FROM ubuntu:24.04 AS runtime
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates python3 python3-yaml novnc websockify \
    tigervnc-standalone-server openbox dbus-x11 \
    libgl1-mesa-dri libglx-mesa0 libgl1 libegl1 libxkbcommon-x11-0 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-xinerama0 libxcb-xinput0 \
    libxrender1 libxrandr2 libxi6 libxfixes3 libxcursor1 libxdamage1 \
    libxtst6 libnss3 libasound2t64 libpulse0 libxss1 \
    fontconfig fonts-dejavu-core fonts-noto-cjk unzip \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1001 engineer

FROM runtime
COPY FreeCAD.AppImage /opt/FreeCAD.AppImage
RUN echo '675d1a4295b2183e0e1d816a4b5557dcb63aeced4e60aaa28d6c3686f4c71dc9  /opt/FreeCAD.AppImage' | sha256sum -c - \
    && chmod +x /opt/FreeCAD.AppImage \
    && cd /opt && ./FreeCAD.AppImage --appimage-extract >/dev/null \
    && rm /opt/FreeCAD.AppImage
COPY GongKeWorkbench.zip /tmp/GongKeWorkbench.zip
RUN mkdir -p /home/engineer/.local/share/FreeCAD/Mod \
    && unzip -q /tmp/GongKeWorkbench.zip -d /home/engineer/.local/share/FreeCAD/Mod \
    && rm /tmp/GongKeWorkbench.zip \
    && chown -R engineer:engineer /home/engineer
COPY start.sh bootstrap.FCMacro /opt/gongke/
RUN chmod +x /opt/gongke/start.sh
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1
ENV HOME=/home/engineer DISPLAY=:1 QT_QPA_PLATFORM=xcb \
    LIBGL_ALWAYS_SOFTWARE=1 PYTHONDONTWRITEBYTECODE=1 \
    FREECAD_USER_HOME=/home/engineer/.local/share/FreeCAD \
    PYTHONPATH=/home/engineer/.local/share/FreeCAD/Mod/GongKeWorkbench
USER engineer
WORKDIR /home/engineer
ENTRYPOINT ["/opt/gongke/start.sh"]
