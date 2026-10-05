# Build, scan and publish this minimal image; SANDBOX_IMAGE must use its digest.
# The orchestrator refuses mutable tags and never pulls at admission time.
FROM python:3.12-slim
RUN groupadd --gid 65532 learner && useradd --uid 65532 --gid learner --no-create-home learner
USER 65532:65532
WORKDIR /tmp
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["/usr/local/bin/python"]
