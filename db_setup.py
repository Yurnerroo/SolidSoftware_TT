"""Create a database and load the schema (and optionally the sample data).

Usage: python db_setup.py [DATABASE_URL]

DATABASE_URL points at the database to create, e.g.
postgresql://USER:PASSWORD@localhost:5432/shop. It defaults to the Docker database.
"""
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

DEFAULT_URL = "postgresql://shop:shop@localhost:5433/shop"
MAINTENANCE_DATABASE = "postgres"
DB_DIR = Path(__file__).parent / "db"
MIGRATIONS = sorted((DB_DIR / "migrations").glob("*.sql"))
SEED = DB_DIR / "seed.sql"


def _connect(url, database: str):
    connection = psycopg2.connect(url.set(drivername="postgresql", database=database).render_as_string(False))
    connection.autocommit = True
    return connection


def create_database(url, recreate: bool = False) -> None:
    """Create the database; with recreate=True drop an existing one first."""
    connection = _connect(url, MAINTENANCE_DATABASE)
    name = sql.Identifier(url.database)
    with connection.cursor() as cursor:
        if recreate:
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(name))
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(name))
    connection.close()


def apply_sql_files(url, files) -> None:
    connection = _connect(url, url.database)
    with connection.cursor() as cursor:
        for file in files:
            cursor.execute(file.read_text(encoding="utf-8"))
    connection.close()


def _fail(message: str) -> None:
    sys.exit(f"db_setup: {message}")


if __name__ == "__main__":
    target = make_url(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL)
    try:
        create_database(target)
    except psycopg2.errors.DuplicateDatabase:
        _fail(f"database '{target.database}' already exists; drop it or choose another name")
    except psycopg2.OperationalError as error:
        _fail(f"cannot connect with the given URL (check user, password, host and port): {error}")
    apply_sql_files(target, [*MIGRATIONS, SEED])
    print(f"Database '{target.database}' is ready.")
