FROM alpine:3.24

WORKDIR /app

ADD server.py /app
ADD templates /app/templates
ADD static /app/static

RUN \
  echo "**** install dependencies ****" && \
  apk add --no-cache wireguard-tools iproute2 iptables openresolv bash curl ca-certificates \
    python3 py3-flask py3-qrcode py3-pillow py3-requests py3-schedule py3-paho-mqtt

EXPOSE 51820/udp
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
