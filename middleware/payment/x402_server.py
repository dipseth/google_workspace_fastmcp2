"""Factory for creating an x402ResourceServer from application settings.

Lazily initializes and caches a singleton ``x402ResourceServer`` instance
configured with the appropriate EVM scheme, facilitator client, and
payment options derived from ``config.settings``.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from typing import TYPE_CHECKING

from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.server import x402ResourceServer

from config.enhanced_logging import setup_logger
from middleware.payment.constants import USDC_CONTRACTS

if TYPE_CHECKING:
    from config.settings import Settings

logger = setup_logger()


@lru_cache(maxsize=1)
def create_resource_server(
    facilitator_url: str,
    network: str,
) -> x402ResourceServer:
    """Create and cache an x402ResourceServer instance.

    Uses ``lru_cache`` with hashable args so the heavy SDK objects are
    built exactly once per process lifetime.
    """
    facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=facilitator_url))
    server = x402ResourceServer(facilitator)
    server.register(network, ExactEvmServerScheme())
    server.initialize()
    logger.info(
        "x402ResourceServer created (facilitator=%s, network=%s)",
        facilitator_url,
        network,
    )
    return server


def build_payment_options(settings: Settings) -> list[PaymentOption]:
    """Build x402 PaymentOption list from application settings."""
    return [
        PaymentOption(
            scheme=settings.payment_scheme,
            network=settings.payment_network,
            pay_to=settings.payment_recipient_wallet,
            price=f"${settings.payment_usdc_amount}",
        ),
    ]


def get_resource_server(settings: Settings) -> x402ResourceServer:
    """Convenience wrapper that reads settings and returns the cached server."""
    return create_resource_server(
        facilitator_url=settings.payment_facilitator_url,
        network=settings.payment_network,
    )


def build_payment_requirements(settings: Settings) -> dict:
    """Build x402 v2 payment requirements dict for 402 responses.

    Uses the SDK's ``build_payment_requirements`` to get properly enhanced
    requirements including EIP-712 domain info in ``extra``.

    Returns a JSON-serializable dict that can be base64-encoded and sent
    in ``meta.x402.paymentRequired``.
    """
    try:
        from x402 import ResourceConfig

        server = get_resource_server(settings)
        config = ResourceConfig(
            scheme=settings.payment_scheme,
            network=settings.payment_network,
            pay_to=settings.payment_recipient_wallet,
            price=f"${settings.payment_usdc_amount}",
        )
        reqs = server.build_payment_requirements(config)
        return {
            "x402Version": 2,
            "accepts": [r.model_dump(by_alias=True) for r in reqs],
        }
    except Exception as e:
        logger.warning("SDK build_payment_requirements failed (%s), using manual", e)
        # Fallback to manual construction
        network = settings.payment_network
        try:
            chain_id = int(network.split(":")[-1])
        except (ValueError, IndexError):
            chain_id = settings.payment_chain_id

        usdc_contract = USDC_CONTRACTS.get(chain_id, "")

        return {
            "x402Version": 2,
            "accepts": [
                {
                    "scheme": settings.payment_scheme,
                    "network": network,
                    "amount": str(int(float(settings.payment_usdc_amount) * 1e6)),
                    "asset": usdc_contract,
                    "payTo": settings.payment_recipient_wallet,
                    "maxTimeoutSeconds": 300,
                    "extra": {"name": "USDC", "version": "2"},
                }
            ],
        }


def encode_payment_requirements(requirements: dict) -> str:
    """Base64-encode a payment requirements dict for transport."""
    return base64.b64encode(json.dumps(requirements).encode("utf-8")).decode("utf-8")
