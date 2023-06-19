FROM python:3.11.4-alpine3.18
COPY ./ /src
WORKDIR /src
RUN apk add gcc musl-dev linux-headers python3-dev --no-cache && python3 -m pip install -r requirements.txt && apk del gcc musl-dev linux-headers python3-dev && apk cache clean
CMD ["python3", "-m", "bot"]
