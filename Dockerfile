FROM python:3.7-slim

RUN apt update
RUN apt install -y build-essential libicu-dev pkg-config

COPY ./ /src
WORKDIR /src

RUN python -m pip install -r requirements/main.txt -r requirements/test.txt
RUN python -m pip install -e "."
