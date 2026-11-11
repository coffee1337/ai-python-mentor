# Execution host. Two isolation backends are supported; see docs/RUNBOOK.md.
#   docker   — requires a host runtime with runsc + cgroups v2 (production default
#              when available; mount the runtime socket into this container).
#   landlock — kernel LSM + seccomp, no privileges, no runtime socket.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RUNNER_SANDBOX_BACKEND=auto

RUN groupadd --gid 10002 runner && useradd --uid 10002 --gid runner --no-create-home --shell /usr/sbin/nologin runner

WORKDIR /app
COPY pyproject.toml ./
COPY runner_worker ./runner_worker
RUN pip install --no-cache-dir . && mkdir -p /var/lib/ai-tutor-runner && chown -R runner:runner /var/lib/ai-tutor-runner

USER runner
EXPOSE 8443
ENTRYPOINT ["python", "-m", "runner_worker.server"]
