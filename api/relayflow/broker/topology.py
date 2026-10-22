from kombu import Exchange, Queue

events = Exchange("relayflow.events", type="topic", durable=True)
dlx = Exchange("relayflow.dlx", type="fanout", durable=True)

_DEAD_LETTER = {"x-dead-letter-exchange": "relayflow.dlx"}

crm = Queue(
    "crm",
    exchange=events,
    routing_key="stripe.#",
    durable=True,
    queue_arguments=_DEAD_LETTER,
)
email = Queue(
    "email",
    exchange=events,
    routing_key="#.completed",
    durable=True,
    queue_arguments=_DEAD_LETTER,
)
audit = Queue(
    "audit",
    exchange=events,
    routing_key="#",
    durable=True,
    queue_arguments=_DEAD_LETTER,
)
dead = Queue("relayflow.dead", exchange=dlx, routing_key="", durable=True)

WORK_QUEUES = (crm, email, audit)
QUEUE_NAMES = ("crm", "email", "audit", "relayflow.dead")


def declare_topology(channel) -> None:
    dead(channel).declare()
    for queue in WORK_QUEUES:
        queue(channel).declare()
    crm(channel).bind_to(events, routing_key="monday.#")


def queue_depths(channel) -> dict[str, int]:
    declare_topology(channel)
    depths: dict[str, int] = {}
    for name in QUEUE_NAMES:
        declared = channel.queue_declare(queue=name, passive=True)
        depths[name] = int(declared[1])
    return depths
