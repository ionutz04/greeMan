# Use specific version instead of latest
FROM alpine:3.19
RUN echo "ver25"
# Use default repositories (no need to overwrite them)
RUN echo "Installing dependencies..." && \
    apk update && \
    apk add --no-cache \
    python3 \
    py3-pip \
    py3-netifaces \
    gcc \
    musl-dev \
    python3-dev \
    wget \
    linux-headers\
    net-snmp-tools


# Create virtual environment properly
# RUN mkdir /app
WORKDIR /app
RUN python3 -m venv /app/venv 
RUN . /app/venv/bin/activate
ENV PATH="/app/venv/bin:$PATH"
# Install Python packages using virtual environment's pip
# RUN source /app/venv/bin/activate
RUN pip install --upgrade pip
RUN pip install netifaces==0.10.9
RUN pip uninstall pycrypto pycryptodome pycryptodomex -y
RUN pip install pycryptodome==3.10.4
#RUN pip install netifaces
#RUN pip install pycrypto
RUN pip install --no-cache-dir greeclimate

# Download controller script (remove token parameter)
# RUN wget https://raw.githubusercontent.com/ionutz04/greeMan/refs/heads/main/scripts/controller.py?token=GHSAT0AAAAAADCKLWH7PGC3HI5ZONX22SNA2AVHC7Q -O /app/controller.py
# COPY ./controller.py /app/

# Cleanup build dependencies
# RUN apk del gcc musl-dev python3-dev

CMD ["python3", "controller.py"]
# CMD ["tail", "-f", "/dev/null"]
# CMD [ "/bin/sleep 10000" ]
