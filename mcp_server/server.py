import os

import pymysql
from dotenv import load_dotenv
from mcp.server import MCPServer


ENV_FILE = os.path.expanduser("~/smartfarm/mcp_server/.env")
load_dotenv(ENV_FILE)

mcp = MCPServer(
    name="Smart Farm MCP",
    description="Read-only MCP server for Smart Farm MariaDB on PN64",
)


def get_connection():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


@mcp.tool()
def get_database_health() -> dict:
    """
    Check connectivity to the Smart Farm MariaDB database.
    Returns database name, authenticated database user, and MariaDB version.
    """

    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    DATABASE() AS database_name,
                    CURRENT_USER() AS database_user,
                    VERSION() AS database_version
                """
            )

            row = cur.fetchone()

            return {
                "status": "ok",
                "database": row["database_name"],
                "user": row["database_user"],
                "version": row["database_version"],
            }

    finally:
        conn.close()


@mcp.tool()
def get_workers() -> list[dict]:
    """
    Return active Smart Farm workers.
    """

    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    worker_code,
                    worker_name_th,
                    nickname,
                    role,
                    is_active
                FROM m_worker
                WHERE is_active = 1
                ORDER BY id
                """
            )

            return cur.fetchall()

    finally:
        conn.close()


app = mcp.streamable_http_app(
    stateless_http=True,
    json_response=True,
)