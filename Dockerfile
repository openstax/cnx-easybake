FROM python:3

COPY ./ /src
WORKDIR /src

RUN set -x \
    && python -m pip install -r requirements/main.txt -r requirements/test.txt
RUN set -x && python -m pip install -e "."
