FROM public.ecr.aws/docker/library/eclipse-temurin:21-jdk-jammy@sha256:25d1276565738d3c805e632a4542c3a7598866ef967f4def6544c15de3a74b14

ENV TZ=UTC \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    DEBIAN_FRONTEND=noninteractive \
    GRADLE_USER_HOME=/opt/gradle-home

RUN apt-get update && apt-get install -y --no-install-recommends python3=3.10.6-1~22.04.1 python3-pip=22.0.2+dfsg-1ubuntu0.7 \
    git=1:2.34.1-1ubuntu1.17 \
    graphviz=2.42.2-6ubuntu0.1 \
    tmux=3.2a-4ubuntu0.2 \
    asciinema=2.1.0-1 \
    jq=1.6-2.1ubuntu3.2 \
    ca-certificates=20260601~22.04.1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --require-hashes -r /tmp/requirements.txt
RUN rm -f /tmp/requirements.txt

RUN groupadd -g 1000 agent && useradd -m -u 1000 -g 1000 -s /bin/bash agent \
    && mkdir -p /opt/gradle-home /app/bin /app/worktrees /app/fixtures /output /logs/agent /logs/verifier \
    && chown agent:agent /opt/gradle-home /output /logs /logs/agent /logs/verifier

COPY --chown=root:root app-seed/docs/ /app/docs/
COPY --chown=root:root app-seed/scripts/ /app/scripts/
COPY --chown=root:root app-seed/launcher/ /tmp/launcher/
COPY --chown=root:root app-seed/release-repo-seed/ /app/release-repo-seed/
COPY --chown=agent:agent app-seed/environment/ /app/environment/
COPY --chown=root:root data/ /data/
COPY --chown=root:root bootstrap/ /opt/bootstrap/
COPY --chown=root:root VERIFIER.md /app/VERIFIER.md

RUN cp /tmp/launcher/lineage-audit /app/bin/lineage-audit \
    && rm -rf /tmp/launcher \
    && chmod +x /app/bin/lineage-audit /opt/bootstrap/create-release-worktrees.sh /opt/bootstrap/lock-input-permissions.sh \
    && bash /opt/bootstrap/create-release-worktrees.sh

USER agent
WORKDIR /app/environment
RUN chmod +x gradlew \
    && ./gradlew --no-daemon installDist \
    && ./gradlew --no-daemon test

USER root
RUN bash /opt/bootstrap/lock-input-permissions.sh \
    && chown agent:agent /output /logs /logs/agent /logs/verifier \
    && chmod u+rwX /output /logs /logs/agent /logs/verifier

USER root
WORKDIR /app/environment

CMD ["sleep", "infinity"]
