FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app

# 只装猜选手跑得起来的那几个包。Blind Draft(apps/blind_draft、data/blind_draft)
# 整个不进镜像——它是本地原型,而且它的数据里有 12MB 的 5E 照片,进来纯属压舱石。
#
# 包名靠 pyproject.toml 的 package-dir 映射;镜像里直接按映射后的名字平铺到
# /app,所以下面那行 `uvicorn server.main:app` 和目录调整之前一模一样,
# 部署脚本和 compose 的卷路径都不用动。
COPY --chown=app:app packages/playerdb ./playerdb
COPY --chown=app:app apps/guess_the_player/server ./server
COPY --chown=app:app apps/guess_the_player/tools ./gtptools
COPY --chown=app:app apps/guess_the_player/static ./static
COPY --chown=app:app data ./data

# 人工层挂可写卷;目录先建好,免得只读根文件系统上创建挂载点时出岔子。
# 权限放开到组+其他用户是因为 compose 用 user: 覆盖了运行身份(见 compose.yaml)。
RUN mkdir -p /app/data/manual/img && chmod -R 777 /app/data/manual

USER app

EXPOSE 8620

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8620/api/meta', timeout=3)"]

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8620", "--proxy-headers", "--forwarded-allow-ips=*"]
