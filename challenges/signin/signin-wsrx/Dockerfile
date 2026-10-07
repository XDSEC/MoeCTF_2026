FROM python:3.14-alpine

RUN adduser -D ctfuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ templates/

RUN chown -R ctfuser:ctfuser /app
USER ctfuser

EXPOSE 8080

CMD ["python", "app.py"]