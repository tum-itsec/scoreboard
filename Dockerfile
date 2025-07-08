FROM debian:bookworm

RUN apt-get -y update && apt-get install -y python3 python3-pip
RUN pip install --upgrade pip --break-system-packages
COPY requirements.txt /
RUN pip install -r /requirements.txt --break-system-packages
RUN mkdir /home/scoreboard/
WORKDIR /home/scoreboard
CMD gunicorn -w 4 app:app -b 0.0.0.0
