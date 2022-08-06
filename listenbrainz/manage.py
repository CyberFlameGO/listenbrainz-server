import os
from time import sleep

import click
import sqlalchemy

from listenbrainz import db
from listenbrainz import webserver
from listenbrainz.db import timescale as ts
from listenbrainz.listenstore import timescale_fill_userid
from listenbrainz.listenstore.timescale_utils import recalculate_all_user_data as ts_recalculate_all_user_data, \
    update_user_listen_data as ts_update_user_listen_data, \
    add_missing_to_listen_users_metadata as ts_add_missing_to_listen_users_metadata,\
    delete_listens as ts_delete_listens, \
    delete_listens_and_update_user_listen_data as ts_delete_listens_and_update_user_listen_data
from listenbrainz.webserver import create_app, ts_conn


@click.group()
def cli():
    pass


ADMIN_SQL_DIR = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), '..', 'admin', 'sql')
MSB_ADMIN_SQL_DIR = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), '..', 'admin', 'messybrainz', 'sql')
TIMESCALE_SQL_DIR = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), '..', 'admin', 'timescale')


@cli.command(name="run_websockets")
@click.option("--host", "-h", default="0.0.0.0", show_default=True)
@click.option("--port", "-p", default=7082, show_default=True)
@click.option("--debug", "-d", is_flag=True,
              help="Turns debugging mode on or off. If specified, overrides "
                   "'DEBUG' value in the config file.")
def run_websockets(host, port, debug=True):
    from listenbrainz.websockets.websockets import run_websockets
    run_websockets(host=host, port=port, debug=debug)


@cli.command(name="init_db")
@click.option("--force", "-f", is_flag=True, help="Drop existing database and user.")
@click.option("--create-db", is_flag=True, help="Create the database and user.")
def init_db(force, create_db):
    """Initializes database.

    This process involves several steps:
        1. Table structure is created.
        2. Primary keys and foreign keys are created.
        3. Indexes are created.
    """
    from listenbrainz import config
    db.init_db_connection(config.POSTGRES_ADMIN_URI)
    if force:
        res = db.run_sql_script_without_transaction(
            os.path.join(ADMIN_SQL_DIR, 'drop_db.sql'))
        if not res:
            raise Exception(
                'Failed to drop existing database and user! Exit code: %i' % res)

    if create_db or force:
        print('PG: Creating user and a database...')
        res = db.run_sql_script_without_transaction(
            os.path.join(ADMIN_SQL_DIR, 'create_db.sql'))
        if not res:
            raise Exception(
                'Failed to create new database and user! Exit code: %i' % res)

        db.init_db_connection(config.POSTGRES_ADMIN_LB_URI)
        print('PG: Creating database extensions...')
        res = db.run_sql_script_without_transaction(
            os.path.join(ADMIN_SQL_DIR, 'create_extensions.sql'))
    # Don't raise an exception if the extension already exists

    application = webserver.create_app()
    with application.app_context():
        print('PG: Creating schema...')
        db.run_sql_script(os.path.join(ADMIN_SQL_DIR, 'create_schema.sql'))

        print('PG: Creating Types...')
        db.run_sql_script(os.path.join(ADMIN_SQL_DIR, 'create_types.sql'))

        print('PG: Creating tables...')
        db.run_sql_script(os.path.join(ADMIN_SQL_DIR, 'create_tables.sql'))

        print('PG: Creating primary and foreign keys...')
        db.run_sql_script(os.path.join(
            ADMIN_SQL_DIR, 'create_primary_keys.sql'))
        db.run_sql_script(os.path.join(
            ADMIN_SQL_DIR, 'create_foreign_keys.sql'))

        print('PG: Creating indexes...')
        db.run_sql_script(os.path.join(ADMIN_SQL_DIR, 'create_indexes.sql'))

        print("Done!")


@cli.command(name="init_msb_db")
@click.option("--force", "-f", is_flag=True, help="Drop existing database and user.")
@click.option("--create-db", is_flag=True, help="Skip creating database and user. Tables/indexes only.")
def init_msb_db(force, create_db):
    """Initializes database.

    This process involves several steps:
        1. Table structure is created.
        2. Primary keys and foreign keys are created.
        3. Indexes are created.
    """
    from listenbrainz import config
    db.init_db_connection(config.POSTGRES_ADMIN_URI)
    if force:
        res = db.run_sql_script_without_transaction(
            os.path.join(MSB_ADMIN_SQL_DIR, 'drop_db.sql'))
        if not res:
            raise Exception(
                'Failed to drop existing database and user! Exit code: %s' % res)

    if create_db or force:
        print('PG: Creating user and a database...')
        res = db.run_sql_script_without_transaction(
            os.path.join(MSB_ADMIN_SQL_DIR, 'create_db.sql'))
        if not res:
            raise Exception(
                'Failed to create new database and user! Exit code: %s' % res)

    print('PG: Creating database extensions...')
    res = db.run_sql_script_without_transaction(
        os.path.join(MSB_ADMIN_SQL_DIR, 'create_extensions.sql'))
    # Don't raise an exception if the extension already exists

    db.engine.dispose()

#    print('PG: Creating schema...')
#    exit_code = run_psql_script('create_schema.sql')
#    if exit_code != 0:
#        raise Exception('Failed to create database schema! Exit code: %i' % exit_code)

    db.init_db_connection(config.MESSYBRAINZ_SQLALCHEMY_DATABASE_URI)
    print('PG: Creating tables...')
    db.run_sql_script(os.path.join(MSB_ADMIN_SQL_DIR, 'create_tables.sql'))

    print('PG: Creating primary and foreign keys...')
    db.run_sql_script(os.path.join(
        MSB_ADMIN_SQL_DIR, 'create_primary_keys.sql'))
    db.run_sql_script(os.path.join(
        MSB_ADMIN_SQL_DIR, 'create_foreign_keys.sql'))

    print('PG: Creating functions...')
    db.run_sql_script(os.path.join(MSB_ADMIN_SQL_DIR, 'create_functions.sql'))

    print('PG: Creating indexes...')
    db.run_sql_script(os.path.join(MSB_ADMIN_SQL_DIR, 'create_indexes.sql'))

    print("Done!")


@cli.command(name="init_ts_db")
@click.option("--force", "-f", is_flag=True, help="Drop existing database and user.")
@click.option("--create-db", is_flag=True, help="Create the database and user.")
def init_ts_db(force, create_db):
    """Initializes database.

    This process involves several steps:
        1. Table structure is created.
        2. Indexes are created.
        3. Views are created
    """
    from listenbrainz import config
    ts.init_db_connection(config.TIMESCALE_ADMIN_URI)
    if force:
        res = ts.run_sql_script_without_transaction(
            os.path.join(TIMESCALE_SQL_DIR, 'drop_db.sql'))
        if not res:
            raise Exception(
                'Failed to drop existing database and user! Exit code: %i' % res)

    if create_db or force:
        print('TS: Creating user and a database...')
        retries = 0
        while True:
            try:
                res = ts.run_sql_script_without_transaction(
                    os.path.join(TIMESCALE_SQL_DIR, 'create_db.sql'))
                break
            except sqlalchemy.exc.OperationalError:
                print("Trapped template1 access error, FFS! Sleeping, trying again.")
                retries += 1
                if retries == 5:
                    raise
                sleep(1)
                continue

        if not res:
            raise Exception(
                'Failed to create new database and user! Exit code: %i' % res)

        ts.init_db_connection(config.TIMESCALE_ADMIN_LB_URI)
        print('TS: Creating database extensions...')
        res = ts.run_sql_script_without_transaction(
            os.path.join(TIMESCALE_SQL_DIR, 'create_extensions.sql'))
    # Don't raise an exception if the extension already exists

    ts.init_db_connection(config.SQLALCHEMY_TIMESCALE_URI)
    application = webserver.create_app()
    with application.app_context():
        print('TS: Creating Schemas...')
        ts.run_sql_script(os.path.join(
            TIMESCALE_SQL_DIR, 'create_schemas.sql'))

        print('TS: Creating Types...')
        ts.run_sql_script(os.path.join(TIMESCALE_SQL_DIR, 'create_types.sql'))

        print('TS: Creating tables...')
        ts.run_sql_script(os.path.join(TIMESCALE_SQL_DIR, 'create_tables.sql'))

        print('TS: Creating Functions...')
        ts.run_sql_script(os.path.join(
            TIMESCALE_SQL_DIR, 'create_functions.sql'))

        print('TS: Creating indexes...')
        ts.run_sql_script(os.path.join(TIMESCALE_SQL_DIR, 'create_indexes.sql'))

        print('TS: Creating Primary and Foreign Keys...')
        ts.run_sql_script(os.path.join(
            TIMESCALE_SQL_DIR, 'create_primary_keys.sql'))
        ts.run_sql_script(os.path.join(
            TIMESCALE_SQL_DIR, 'create_foreign_keys.sql'))

        print("Done!")


@cli.command(name="update_user_emails")
def update_user_emails():
    from listenbrainz.webserver.login import copy_files_from_mb_to_lb
    application = webserver.create_app()
    with application.app_context():
        copy_files_from_mb_to_lb.copy_emails()


@cli.command(name="set_rate_limits")
@click.argument("per_token_limit", type=click.IntRange(1, None))
@click.argument("per_ip_limit", type=click.IntRange(1, None))
@click.argument("window_size", type=click.IntRange(1, None))
def set_rate_limits(per_token_limit, per_ip_limit, window_size):
    from brainzutils.ratelimit import set_rate_limits
    application = webserver.create_app()
    with application.app_context():
        set_rate_limits(per_token_limit, per_ip_limit, window_size)


@cli.command(name="recalculate_all_user_data")
def recalculate_all_user_data():
    """ Recalculate all user timestamps and listen counts.

    .. note::
        **ONLY USE THIS WHEN YOU KNOW WHAT YOU ARE DOING!**
    """
    application = webserver.create_app()
    with application.app_context():
        ts_recalculate_all_user_data()


@cli.command(name="update_user_listen_data")
def update_user_listen_data():
    """ Scans listen table and update listen metadata for all users """
    application = webserver.create_app()
    with application.app_context():
        ts_update_user_listen_data()


@cli.command(name="delete_pending_listens")
def delete_pending_listens():
    """ Complete all pending listen deletes since last cron run """
    application = webserver.create_app()
    with application.app_context():
        ts_delete_listens(ts_conn)


@cli.command(name="delete_listens_and_update_metadata")
def delete_listens_and_update_metadata():
    """ Complete all pending listen deletes and also run update script for
    updating listen metadata since last cron run """
    application = webserver.create_app()
    with application.app_context():
        ts_delete_listens_and_update_user_listen_data(ts_conn)


@cli.command(name="add_missing_to_listen_users_metadata")
def add_missing_to_listen_users_metadata():
    application = webserver.create_app()
    with application.app_context():
        ts_add_missing_to_listen_users_metadata()


@cli.command()
@click.option("-u", "--user", type=str)
@click.option("-t", "--token", type=str)
@click.argument("releasembid", type=str)
def submit_release(user, token, releasembid):
    """Submit a release from MusicBrainz to the local ListenBrainz instance

    Specify -u to use the token of this user when submitting, or
    -t to specify a specific token.
    """
    if user is None and token is None:
        raise click.ClickException(f"Need --user or --token")
    if user is not None:
        import listenbrainz.db.user
        application = webserver.create_app()
        with application.app_context():
            user_ob = listenbrainz.db.user.get_by_mb_id(user)
            if user_ob is None:
                raise click.ClickException(f"No such user: {user}")
            token = user_ob["auth_token"]
            print("token is", token)
    import listenbrainz.misc.submit_release
    listenbrainz.misc.submit_release.submit_release_impl(token, releaseid, "http://web:7000")


@cli.command(name="notify_yim_users")
def notify_yim_users():
    application = webserver.create_app()
    with application.app_context():
        from listenbrainz.db import year_in_music
        year_in_music.notify_yim_users()


@cli.command()
def listen_add_userid():
    """
        Fill in the listen.user_id field based on user_name.
    """
    app = create_app()
    with app.app_context():
        timescale_fill_userid.fill_userid()
