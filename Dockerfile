FROM debian

RUN \
	apt-get -y update \
	&& apt-get install -y --no-install-recommends python3-venv \
	&& rm -rf /var/cache/apt /var/lib/apt/lists/*
RUN python3 -m venv /venv
RUN mkdir /app
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN /venv/bin/pip install -r requirements.txt
COPY --chmod=755 run.sh run-docker.sh /
COPY --parents app.py db board plugins static templates /app
RUN mkdir /data

VOLUME /data
CMD /run-docker.sh
