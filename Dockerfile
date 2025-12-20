FROM python:3.14-alpine
COPY ./requirements.txt /src/
WORKDIR /src
RUN apk add gcc musl-dev linux-headers python3-dev --no-cache \
    && python3 -m pip install --no-cache-dir -r requirements.txt \
    && rm -rf /root/.cache/pip \
    && apk del gcc musl-dev linux-headers python3-dev \
    && apk cache clean
COPY ./ /src
CMD ["python3", "-m", "bot"]
