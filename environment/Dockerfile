FROM public.ecr.aws/docker/library/maven:3.9.9-eclipse-temurin-21@sha256:3a4ab3276a087bf276f79cae96b1af04f53731bec53fb2e651aca79e4b10211e

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3=3.12.3-0ubuntu2.1 \
    python3-venv=3.12.3-0ubuntu2.1 \
    python3-pip=24.0+dfsg-1ubuntu1.3 \
    tmux=3.4-1ubuntu0.1 \
    asciinema=2.4.0-1 \
    libsqlite3-0=3.45.1-1ubuntu2.7 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5 \
        pytest-randomly==3.16.0
ENV PATH=/opt/verifier/bin:${PATH}

# Prefetch Maven artifacts while build network is available.
COPY pom.xml /app/pom.xml
COPY core/pom.xml /app/core/pom.xml
COPY k1/pom.xml /app/k1/pom.xml
COPY k2/pom.xml /app/k2/pom.xml
COPY k3/pom.xml /app/k3/pom.xml
COPY drive/pom.xml /app/drive/pom.xml
RUN mkdir -p \
    /app/core/src/main/java \
    /app/k1/src/main/java \
    /app/k2/src/main/java \
    /app/k3/src/main/java \
    /app/drive/src/main/java \
    && mvn -q -DskipTests dependency:go-offline

COPY . /app
