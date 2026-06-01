# hash:sha256:0f8163c67d1218a257458b6dfcf7b91d0d935a3a443020cfcd1f9dc2d79aa36b
ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/jupyterlab:3.4.4-miniconda4.12.0-python3.9-ubuntu20.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GIT_ASKPASS
COPY git-ask-pass /

RUN pip3 install -U --no-cache-dir \
    aind-data-schema==1.2.0 \
    aind-log-utils \
    aind-ophys-utils \
    aind-qcportal-schema \
    matplotlib \
    pydantic==2.8.2 \
    pydantic-settings
