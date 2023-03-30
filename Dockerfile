FROM debian

WORKDIR /app

ADD server.py /app
ADD templates /opt/wirevad/templates
ADD static /opt/wirevad/static

RUN \
  echo "**** install dependencies ****" && \
  apt-get update && \
  apt-get install -y --no-install-recommends wireguard-tools iproute2 openresolv sudo curl iptables ca-certificates procps iputils-ping net-tools python3 pip && \
  pip install qrcode flask requests schedule

RUN useradd -m docker && echo "docker:docker" | chpasswd && adduser docker sudo

EXPOSE 51822
EXPOSE 8000

CMD ["python3", "-u", "server.py"]

#The following is from https://www.devopsforit.com/posts/anatomy-of-a-dockerfile-build-a-docker-image

#FROM : This command builds an initial layer from an existing image (ever image is based on another image)
#WORKDIR: defining the working directory
#COPY: copy file from client/local device to the image
#ADD: add/copy files from client/local device to the image (similar to COPY)
#RUN: run a command during the image build (used for installing dependencies)
#CMD: execute a command after the container has been created
#ENV: define the environment
#EXPOSE: expose a port
#USER: define a user
#ENTRYPOINT: define an entrypoint to the container
