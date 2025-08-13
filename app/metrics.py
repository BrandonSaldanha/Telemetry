# app/metrics.py
import time
from prometheus_client import Counter, Histogram, Gauge, REGISTRY, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Latency of HTTP requests in seconds",
    ["method", "path"]
)
INPROGRESS = Gauge("inprogress_requests", "In-progress requests")

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        method = request.method
        path = request.url.path
        if path == "/metrics":
            # don’t measure the metrics endpoint itself
            return await call_next(request)

        start = time.perf_counter()
        INPROGRESS.inc()
        try:
            response = await call_next(request)
            status = getattr(response, "status_code", 500)
            REQUEST_COUNT.labels(method=method, path=path, status_code=str(status)).inc()
            return response
        finally:
            duration = time.perf_counter() - start
            REQUEST_LATENCY.labels(method=method, path=path).observe(duration)
            INPROGRESS.dec()

def metrics_endpoint():
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
