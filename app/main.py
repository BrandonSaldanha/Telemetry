# app/main.py
import asyncio
import os
import random
import time
from typing import Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import requests

# --- Logging (JSON with trace correlation) ---
import logging
from pythonjsonlogger import jsonlogger
import structlog

# --- Prometheus metrics middleware/handler ---
from .metrics import PrometheusMiddleware, metrics_endpoint

# --- OpenTelemetry ---
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

SERVICE_NAME = os.getenv("SERVICE_NAME", "obs-demo-api")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")  # e.g. http://otel-collector:4318

# ----- Logging setup -----
handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
handler.setFormatter(formatter)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(handler)

# structlog wraps stdlib and can enrich with trace ids
def add_trace_context(logger, method_name, event_dict):
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict

structlog.configure(
    processors=[add_trace_context, structlog.processors.JSONRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)
log = structlog.get_logger("app")

# ----- OpenTelemetry Tracing -----
resource = Resource.create({"service.name": SERVICE_NAME})
provider = TracerProvider(resource=resource)
span_exporters = []

if OTEL_EXPORTER_OTLP_ENDPOINT:
    span_exporters.append(OTLPSpanExporter(endpoint=f"{OTEL_EXPORTER_OTLP_ENDPOINT}/v1/traces"))
else:
    # local dev fallback: print spans to console
    span_exporters.append(ConsoleSpanExporter())

for exporter in span_exporters:
    provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

# ----- App -----
app = FastAPI(title="Observability Demo API", version="0.1.0")
app.add_middleware(PrometheusMiddleware)

# auto-instrument FastAPI & outbound HTTP
FastAPIInstrumentor.instrument_app(app)
RequestsInstrumentor().instrument()

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    return metrics_endpoint()

@app.get("/work")
def work(cpu_ms: int = 100, mem_mb: int = 0) -> Dict[str, float]:
    """
    Simulate CPU and/or memory usage.
    cpu_ms: busy-loop milliseconds
    mem_mb: allocate a bytes buffer of roughly this size in MB (freed after)
    """
    start = time.perf_counter()
    buf = None
    if mem_mb > 0:
        buf = bytearray(mem_mb * 1024 * 1024)

    # Busy-loop for cpu_ms
    target = start + (cpu_ms / 1000.0)
    x = 0
    while time.perf_counter() < target:
        x += 1

    # touch memory so it's not optimized away
    if buf is not None:
        for i in range(0, len(buf), max(1, len(buf)//10)):
            buf[i] = (buf[i] + 1) % 255

    elapsed = time.perf_counter() - start
    log.info("work_done", cpu_ms=cpu_ms, mem_mb=mem_mb, elapsed=elapsed, iters=x)
    return {"elapsed_seconds": elapsed}

@app.get("/downstream")
def downstream():
    """
    Demonstrate outbound HTTP (generates child spans via requests instrumentation).
    """
    with tracer.start_as_current_span("call_httpbin"):
        try:
            r = requests.get("https://httpbin.org/delay/0.2", timeout=3)
            return JSONResponse({"status_code": r.status_code})
        except requests.RequestException as e:
            log.error("downstream_error", error=str(e))
            raise HTTPException(status_code=502, detail="downstream call failed")

@app.get("/db")
async def db_simulated(latency_ms: int = 50):
    """
    Simulate a DB call by sleeping; later you can wire real Postgres here.
    """
    with tracer.start_as_current_span("db_query"):
        await asyncio.sleep(latency_ms / 1000.0)
    return {"rows": 1, "latency_ms": latency_ms}
