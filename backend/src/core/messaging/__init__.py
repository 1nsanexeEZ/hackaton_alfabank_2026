"""Messaging between modules: Kafka topics, integration contracts, transactional
outbox (publishing) and inbox (idempotent consuming).

Rules:
- a module writes to another module only with a command through the outbox;
- every message is an IntegrationMessage from `contracts`, wrapped in an Envelope;
- the partition key of everything about a credit application is its id, so all
  messages of one application are processed in order;
- a reply to a command carries `causation_id = event_id of the command`.
"""
