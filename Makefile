.PHONY: build run logs lint

build:
\tdocker build -t obs-demo-api:local -f app/Dockerfile .

run:
\tdocker run --rm -p 8080:8080 --name obs-demo obs-demo-api:local

logs:
\tdocker logs -f obs-demo

smoke:
\tcurl -s localhost:8080/healthz | jq .
\tcurl -s localhost:8080/work?cpu_ms=200 | jq .
\tcurl -s localhost:8080/metrics | head -50