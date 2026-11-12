def main() -> None:
    """Start the local API server."""

    import uvicorn

    uvicorn.run(
        "webhook_delivery_platform.main:app",
        host="127.0.0.1",
        port=8000,
    )
