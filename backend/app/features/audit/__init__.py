"""Audit event schema and reserved persistence seams."""

from app.features.audit.event_model import SourceAwareAuditEvent

__all__ = ["SourceAwareAuditEvent"]
