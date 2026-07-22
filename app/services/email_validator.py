"""
Email validation abstraction.

The default implementation performs an MX-record DNS lookup to verify that
the email domain has at least one mail server configured.  A paid
deliverability API (ZeroBounce, MillionVerifier, etc.) can be swapped in
later by subclassing EmailValidator and replacing the module-level
`default_validator` instance — no changes to auth_service are required.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import dns.exception
import dns.resolver
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

_MX_ERROR_MSG = "Проверь адрес — такой почтовый домен не найден"


class EmailValidator(ABC):
    """Abstract base for email validators used at registration time."""

    @abstractmethod
    async def validate(self, email: str) -> None:
        """
        Validate *email*.

        Raises
        ------
        HTTPException(422)
            When the email address is considered undeliverable.
        """


class MXRecordEmailValidator(EmailValidator):
    """
    Validates that the email domain has at least one MX record.

    All DNS error conditions (NXDOMAIN, NoAnswer, Timeout, NoNameservers)
    are treated identically: the domain has no reachable mail server.
    """

    async def validate(self, email: str) -> None:
        domain = email.rsplit("@", 1)[-1]
        try:
            dns.resolver.resolve(domain, "MX")
        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.exception.Timeout,
            dns.resolver.NoNameservers,
        ):
            logger.debug("MX lookup failed for domain '%s'", domain)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_MX_ERROR_MSG,
            )
        except Exception:
            # Unexpected DNS library error — log and let through to avoid
            # blocking legitimate signups due to transient resolver issues.
            logger.exception("Unexpected error during MX lookup for domain '%s'", domain)


# Module-level singleton; swap this out to use a different validator without
# modifying any call-site code.
default_validator: EmailValidator = MXRecordEmailValidator()
