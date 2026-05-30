import sqlite3
import pytest
from data.anne import build_index, query_index


@pytest.fixture
def conn():
    pages = [(1, "Democracy requires free institutions and open debate."),
             (2, "Autocracy consolidates power by undermining opposition.")]
    conn = build_index(pages, db_path=":memory:")
    yield conn
    conn.close()


def test_build_index_returns_connection(conn):
    assert isinstance(conn, sqlite3.Connection)


def test_query_returns_results(conn):
    results = conn.execute(
        "SELECT page_num FROM search_index WHERE content MATCH 'democracy'"
    ).fetchall()
    assert len(results) == 1
    assert results[0][0] == 1


def test_query_index_no_match(conn, capsys):
    query_index(conn, "xyznonexistent")
    captured = capsys.readouterr()
    assert "No matches found" in captured.out


def test_query_index_match(conn, capsys):
    query_index(conn, "autocracy")
    captured = capsys.readouterr()
    assert "PAGE 2" in captured.out
