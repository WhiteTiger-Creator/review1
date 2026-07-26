# Canonical Terminus Edition 2 Maven builder image.
FROM public.ecr.aws/docker/library/maven:3.9.9-eclipse-temurin-21@sha256:3a4ab3276a087bf276f79cae96b1af04f53731bec53fb2e651aca79e4b10211e AS dependencies

WORKDIR /build
COPY app/pom.xml ./pom.xml
RUN mvn -B -q dependency:copy-dependencies \
    -DincludeScope=runtime \
    -DoutputDirectory=/deps

# Canonical Terminus Edition 2 Java JDK runtime image.
FROM public.ecr.aws/docker/library/eclipse-temurin:21-jdk-jammy@sha256:25d1276565738d3c805e632a4542c3a7598866ef967f4def6544c15de3a74b14

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        python3 \
        python3-pip \
        tmux \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir \
    pytest==8.4.1 \
    pytest-json-ctrf==0.3.5

WORKDIR /app
COPY --from=dependencies /deps/ /app/lib/
COPY app/ /app/

RUN chmod 0755 /app/bin/weka-cv-audit \
    && /app/bin/weka-cv-audit --help >/dev/null

CMD ["bash"]
