"""Static checks on the migration files. No database is needed, and it catches
the mistake that actually happened once: two migrations adding the same column,
which only fails when the second one runs against a real database."""

import re
from pathlib import Path

MIGRATIONS = sorted((Path(__file__).resolve().parents[2] / "migrations").glob("*.sql"))


def sql_of(path: Path) -> str:
    return re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))


def test_migration_numbers_are_unique_and_contiguous():
    numbers = [int(p.name.split("_")[0]) for p in MIGRATIONS]

    assert numbers == list(range(1, len(numbers) + 1))


def test_no_migration_creates_or_adds_something_that_already_exists():
    tables: dict[str, set[str]] = {}
    indexes: set[str] = set()
    for path in MIGRATIONS:
        sql = sql_of(path)
        for name, body in re.findall(r"CREATE TABLE (\w+)\s*\((.*?)\n\);", sql, re.S):
            assert name not in tables, f"{path.name}: table {name} already exists"
            tables[name] = {
                m.group(1)
                for m in re.finditer(r"^\s+(\w+)\s+[A-Z]", body, re.M)
                if m.group(1).upper() not in {"PRIMARY", "CONSTRAINT", "UNIQUE", "CHECK", "FOREIGN"}
            }
        for table, added in re.findall(r"ALTER TABLE (\w+)\s+((?:ADD COLUMN[^;]*))", sql):
            for column in re.findall(r"ADD COLUMN (\w+)", added):
                assert table in tables, f"{path.name}: alters unknown table {table}"
                assert column not in tables[table], f"{path.name}: {table}.{column} already exists"
                tables[table].add(column)
        for index in re.findall(r"CREATE (?:UNIQUE )?INDEX (\w+)", sql):
            assert index not in indexes, f"{path.name}: index {index} already exists"
            indexes.add(index)
