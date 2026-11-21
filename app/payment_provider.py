import uuid
from dataclasses import dataclass


class ProviderUnavailable(Exception):
    """The payment provider could not be reached or gave no answer."""


@dataclass(frozen=True)
class ChargeResult:
    succeeded: bool
    reference: str | None = None
    failure_reason: str | None = None


class MockPaymentProvider:
    """Stands in for the real provider.

    Tokens starting with "tok_decline" are declined, tokens starting with
    "tok_outage" simulate an unreachable provider, everything else succeeds.
    """

    def charge(self, token: str, amount, currency: str, idempotency_key: str) -> ChargeResult:
        if token.startswith("tok_outage"):
            raise ProviderUnavailable("mock provider outage")
        if token.startswith("tok_decline"):
            return ChargeResult(succeeded=False, failure_reason="card_declined")
        return ChargeResult(succeeded=True, reference=f"mock_{uuid.uuid4().hex}")
