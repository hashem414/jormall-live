from run import app


@app.get("/health")
def container_health():
    return {"status": "healthy", "service": "spin-api"}, 200
