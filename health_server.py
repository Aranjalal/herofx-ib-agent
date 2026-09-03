#!/usr/bin/env python3
"""
Health check server for Railway
Runs alongside the bot to respond to Railway's health checks
"""

import logging
from aiohttp import web

logger = logging.getLogger(__name__)


async def health_handler(request):
    """Handle health check requests."""
    return web.Response(text="OK", status=200)


async def start_health_server(port=8080):
    """Start a simple health check server."""
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check server started on port {port}")
    return runner
