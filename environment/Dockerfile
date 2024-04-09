FROM registry.codeocean.allenneuraldynamics.org/codeocean/jupyterlab:3.4.4-miniconda4.12.0-python3.9-ubuntu20.04

ARG DEBIAN_FRONTEND=noninteractive
ENV AIND_OPHYS_UTILS_VERSION="0.0.7"
ENV AIND_OPHYS_UTILS_REPO_URL=https://github.com/AllenNeuralDynamics/aind-ophys-utils

ARG GIT_ASKPASS
ARG GIT_ACCESS_TOKEN
COPY git-askpass /

RUN ["apt-get", "update"]
RUN ["apt-get", "install", "-y", "vim"]
RUN pip3 install -U --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN pip3 install -U --no-cache-dir \
    aind-ophys-utils==0.0.7 \
    aind-data-schema==0.22.0
