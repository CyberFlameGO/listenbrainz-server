from typing import Optional

from kombu import Connection, pools, producers
from kombu.pools import ProducerPool

from listenbrainz.utils import get_fallback_connection_name

rabbitmq: Optional[ProducerPool] = None

CONNECTION_RETRIES = 10
CONNECTION_LIMIT = 25


def init_rabbitmq_connection(app):
    """Initialize the webserver rabbitmq connection.

    This initializes _rabbitmq as a connection pool from which new RabbitMQ
    connections can be acquired.
    """
    global rabbitmq

    if rabbitmq is not None:
        return

    # if RabbitMQ config values are not in the config file
    # raise an error. This is caught in create_app, so the app will continue running.
    # Consul will bring the values back into config once the RabbitMQ service comes up.
    if "RABBITMQ_HOST" not in app.config:
        app.logger.critical("RabbitMQ host:port not defined, cannot create RabbitMQ connection...")
        raise ConnectionError("RabbitMQ service is not up!")

    connection = Connection(
        hostname=app.config["RABBITMQ_HOST"],
        userid=app.config["RABBITMQ_USERNAME"],
        port=app.config["RABBITMQ_PORT"],
        password=app.config["RABBITMQ_PASSWORD"],
        virtual_host=app.config["RABBITMQ_VHOST"],
        transport_options={"client_properties": {"connection_name": get_fallback_connection_name()}},
    ).ensure_connection(max_retries=CONNECTION_RETRIES)
    pools.set_limit(CONNECTION_LIMIT)
    rabbitmq = producers[connection]
