# Build, scan and publish this minimal image; SANDBOX_IMAGE must use its digest.
# The orchestrator refuses mutable tags and never pulls at admission time.
FROM python:3.12-slim
# No shell and no package tooling: learner code can only run the interpreter, so
# subprocess.run(['/bin/sh', ...]) is not a way out of the box.
RUN groupadd --gid 65532 learner && useradd --uid 65532 --gid learner --no-create-home learner \
    && rm -f /bin/sh /bin/dash /bin/bash /usr/bin/sh /usr/bin/apt /usr/bin/apt-get \
       /usr/bin/apt-cache /usr/bin/apt-config /usr/bin/dpkg /usr/bin/dpkg-deb \
    && rm -rf /var/lib/apt/lists /usr/share/doc /usr/share/man
USER 65532:65532
WORKDIR /tmp
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["/usr/local/bin/python"]
