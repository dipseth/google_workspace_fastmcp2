"""X402 Payment Protocol middleware for tool access gating.

Exports resolve lazily: the x402 SDK ships in the optional [payment] extra,
and submodules such as ``cost_tracker`` are imported by sampling code even
when payments are disabled.
"""

__all__ = ["X402PaymentMiddleware", "create_resource_server", "get_resource_server"]


def __getattr__(name: str):
    if name == "X402PaymentMiddleware":
        from middleware.payment.middleware import X402PaymentMiddleware

        return X402PaymentMiddleware
    if name in ("create_resource_server", "get_resource_server"):
        from middleware.payment import x402_server

        return getattr(x402_server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
