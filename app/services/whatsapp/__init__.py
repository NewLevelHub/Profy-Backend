"""WhatsApp of the sales team (ТЗ §3.5): leads from incoming messages, the
chat in the deal's card, messages to the client.

The provider sits behind `provider.WhatsAppProvider` (ТЗ §3.5, И-05): Green
API now (`green_api.py`), a stub in tests (`fake.py`); the official WhatsApp
Business Platform later. The CRM (`intake.py`, `chat.py`) only sees
`provider.Event`s and `provider.get()`.
"""
