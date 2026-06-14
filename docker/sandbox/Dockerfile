# fleetent agent 专用沙箱镜像（run_code 在此容器内执行）。
#
# 目的：把常用「文件操作 / 数据处理 / 图表」库**烤进镜像**，让 run_code 在
# `--network none` 的封闭沙箱里也能直接 `import openpyxl / pandas / docx / PIL ...`
# 生成 xlsx/docx/pdf/png 等并写入 /workspace，再由 send_file 发出 —— 全程不需运行时联网。
#
# 与仓库根 ./Dockerfile（fleetent 服务镜像）无关：那个装 app，这个只做沙箱执行环境。
# 基础镜像沿用沙箱当前默认 python:3.12-slim，保持 glibc/wheel 兼容。
#
# 构建：
#   docker build -t fleetent-sandbox:0.1.0 -f docker/sandbox/Dockerfile docker/sandbox
# 接入（让 DockerBackend 用它，见 PR 说明）：platform.yaml
#   sandbox:
#     image: fleetent-sandbox:0.1.0
#
# 安全：本镜像不装任何网络/出网库；沙箱运行时仍由 fleetent 加 --network none /
# --read-only / --user / tmpfs 等隔离，镜像只提供"能产文件"的纯计算依赖。

FROM python:3.12-slim

# matplotlib 文字渲染需要字体；其余库走 manylinux wheel，无需额外 build 依赖。
# apt 层单独成层并清理缓存，保持镜像精简。
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# 预装文件操作依赖（固定版本，见 requirements.txt）。--no-cache-dir 不留 pip 缓存。
COPY requirements.txt /tmp/sandbox-requirements.txt
RUN pip install --no-cache-dir -r /tmp/sandbox-requirements.txt \
    && rm -f /tmp/sandbox-requirements.txt

# matplotlib 用无界面后端（沙箱无显示），并预建字体缓存，避免首次 run_code 卡顿。
ENV MPLBACKEND=Agg
RUN python -c "import matplotlib.pyplot as _; import openpyxl, pandas, docx, PIL, reportlab, fpdf, pypdf, tabulate; print('sandbox libs ok')"

# 不设 ENTRYPOINT/CMD：fleetent 在 `docker run` 时显式传入执行命令与工作目录。
