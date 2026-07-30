FROM public.ecr.aws/docker/library/maven:3.9.9-eclipse-temurin-21@sha256:3a4ab3276a087bf276f79cae96b1af04f53731bec53fb2e651aca79e4b10211e

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3=3.12.3-0ubuntu2.1 \
        python3-pip=24.0+dfsg-1ubuntu1.3 \
        python3-venv=3.12.3-0ubuntu2.1 \
        tmux=3.4-1ubuntu0.1 \
        asciinema=2.4.0-1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /opt/verifier/requirements.txt
RUN python3 -m venv /opt/verifier \
    && /opt/verifier/bin/pip install --no-cache-dir --require-hashes \
        -r /opt/verifier/requirements.txt

ENV PATH=/opt/verifier/bin:/opt/java/openjdk/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN mkdir -p /app/output /app/build /logs/verifier

COPY . /app

RUN ln -sfn /app /app/environment

CMD ["python3", "-c", "print('Environment ready')"]
