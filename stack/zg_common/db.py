import json, psycopg
from psycopg.rows import dict_row
from .config import PG_DSN

def connect():
    return psycopg.connect(PG_DSN, autocommit=True, row_factory=dict_row)

_conn = None
def conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = connect()
    return _conn

def q(sql, *args):
    with conn().cursor() as c:
        c.execute(sql, args)
        return c.fetchall() if c.description else []

def q1(sql, *args):
    r = q(sql, *args)
    return r[0] if r else None

def J(v):
    return json.dumps(v, default=str)
