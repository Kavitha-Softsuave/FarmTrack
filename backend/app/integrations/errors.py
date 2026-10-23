"""Errors raised by the integration adapters."""
from __future__ import annotations


class IntegrationError(RuntimeError):
    """Base class: an external system could not be reached or answered badly."""


class NotConfigured(IntegrationError):  # noqa: N818  reads better than NotConfiguredError at call sites
    """A real provider was selected but its credentials or optional dependencies are missing."""


class WeatherUnavailable(IntegrationError):
    """No weather could be produced for the requested place and time."""


class ZohoError(IntegrationError):
    """Zoho CRM returned an error or an unexpected payload."""
