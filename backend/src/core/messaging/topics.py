"""Kafka topics. Key of every message about an application — its id;
`clients.events` — organization id; `identity.events` — account id."""

IDENTITY_EVENTS = "identity.events"
CLIENTS_EVENTS = "clients.events"
APPLICATIONS_EVENTS = "applications.events"
APPLICATIONS_COMMANDS = "applications.commands"
PROCESS_EVENTS = "process.events"
ENRICHMENT_COMMANDS = "enrichment.commands"
ENRICHMENT_EVENTS = "enrichment.events"
SCORING_COMMANDS = "scoring.commands"
SCORING_EVENTS = "scoring.events"
DECISION_COMMANDS = "decision.commands"
DECISION_EVENTS = "decision.events"

ALL_TOPICS: tuple[str, ...] = (
    IDENTITY_EVENTS,
    CLIENTS_EVENTS,
    APPLICATIONS_EVENTS,
    APPLICATIONS_COMMANDS,
    PROCESS_EVENTS,
    ENRICHMENT_COMMANDS,
    ENRICHMENT_EVENTS,
    SCORING_COMMANDS,
    SCORING_EVENTS,
    DECISION_COMMANDS,
    DECISION_EVENTS,
)

DLQ_SUFFIX = ".dlq"


def dead_letter_topic(topic: str) -> str:
    return f"{topic}{DLQ_SUFFIX}"


ALL_TOPICS_WITH_DLQ: tuple[str, ...] = ALL_TOPICS + tuple(dead_letter_topic(t) for t in ALL_TOPICS)
