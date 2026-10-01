"""Pluggable integrations (email, SMS, storage, AI, payments, ...).

Each kind has a small interface in <kind>/base.py and a factory that picks the
implementation from settings, so business code never imports a vendor SDK.
"""
