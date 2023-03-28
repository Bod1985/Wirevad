FROM debian

WORKDIR /app

ADD setup.sh /app

RUN \
  echo "**** install dependencies ****" && \
  apt-get update && \
  apt-get install -y --no-install-recommends wireguard-tools iproute2 openresolv sudo curl iptables ca-certificates procps iputils-ping net-tools

RUN useradd -m docker && echo "docker:docker" | chpasswd && adduser docker sudo

RUN ["chmod", "+x", "/app/setup.sh"]
EXPOSE 51822
CMD ["./app/setup.sh"]

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
