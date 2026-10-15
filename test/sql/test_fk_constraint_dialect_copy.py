# Copyright 2026 the SQLAlchemy authors and contributors
#
# SPDX-License-Identifier: MIT

"""Keep foreign key dialect options through metadata cloning."""

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import Table
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import AddConstraint
from sqlalchemy.testing import fixtures


class ForeignKeyDialectCopyTest(fixtures.TestBase):
    def _check_copy(self, *, column_bound, not_valid):
        metadata = MetaData()
        parent = Table(
            "parent",
            metadata,
            Column("id", Integer, primary_key=True),
        )
        if column_bound:
            args = (
                Column(
                    "parent_id",
                    Integer,
                    ForeignKey(
                        "parent.id",
                        name="fk_parent",
                        postgresql_not_valid=not_valid,
                    ),
                ),
            )
        else:
            args = (
                Column("parent_id", Integer),
                ForeignKeyConstraint(
                    ["parent_id"],
                    ["parent.id"],
                    name="fk_parent",
                    postgresql_not_valid=not_valid,
                ),
            )
        child = Table(
            "child",
            metadata,
            Column("id", Integer, primary_key=True),
            *args,
        )
        copy_metadata = MetaData()
        parent.to_metadata(copy_metadata)
        copy = child.to_metadata(copy_metadata)

        def foreign_key(table):
            return next(
                c
                for c in table.constraints
                if isinstance(c, ForeignKeyConstraint)
            )

        original_fk = foreign_key(child)
        copied_fk = foreign_key(copy)
        assert dict(copied_fk.dialect_kwargs) == dict(
            original_fk.dialect_kwargs
        )
        assert copied_fk.dialect_kwargs["postgresql_not_valid"] is not_valid
        ddl = str(
            AddConstraint(copied_fk).compile(
                dialect=postgresql.dialect()
            )
        )
        assert ddl.endswith(" NOT VALID") is not_valid

        next_metadata = MetaData()
        copy_metadata.tables["parent"].to_metadata(next_metadata)
        twice = copy.to_metadata(next_metadata)
        twice_fk = foreign_key(twice)
        assert dict(twice_fk.dialect_kwargs) == dict(
            original_fk.dialect_kwargs
        )
        twice_ddl = str(
            AddConstraint(twice_fk).compile(
                dialect=postgresql.dialect()
            )
        )
        assert twice_ddl == ddl

    def test_column_not_valid(self):
        self._check_copy(column_bound=True, not_valid=True)

    def test_column_valid(self):
        self._check_copy(column_bound=True, not_valid=False)

    def test_constraint_not_valid(self):
        self._check_copy(column_bound=False, not_valid=True)

    def test_constraint_valid(self):
        self._check_copy(column_bound=False, not_valid=False)

    def _check_other_options(self, *, composite):
        metadata = MetaData()
        parent = Table(
            "parent",
            metadata,
            Column("x", Integer, primary_key=True),
            Column("y", Integer),
        )
        columns = ["x_id", "y_id"] if composite else ["x_id"]
        targets = ["parent.x", "parent.y"] if composite else ["parent.x"]
        child = Table(
            "child",
            metadata,
            Column("x_id", Integer),
            Column("y_id", Integer),
            ForeignKeyConstraint(
                columns,
                targets,
                name="fk_test",
                postgresql_not_valid=True,
                deferrable=True,
                initially="DEFERRED",
                ondelete="CASCADE",
            ),
            UniqueConstraint(
                "x_id",
                name="uq_test",
                postgresql_nulls_not_distinct=True,
            ),
        )
        copy_metadata = MetaData()
        parent.to_metadata(copy_metadata)
        copied = child.to_metadata(copy_metadata)
        constraints = {c.name: c for c in copied.constraints}
        fk = constraints["fk_test"]
        assert fk.dialect_kwargs["postgresql_not_valid"] is True
        assert constraints["uq_test"].dialect_kwargs[
            "postgresql_nulls_not_distinct"
        ] is True
        assert fk.deferrable is True
        assert fk.initially == "DEFERRED"
        assert fk.ondelete == "CASCADE"
        ddl = str(
            AddConstraint(fk).compile(
                dialect=postgresql.dialect()
            )
        )
        assert "NOT VALID" in ddl

    def test_single_options(self):
        self._check_other_options(composite=False)

    def test_composite_options(self):
        self._check_other_options(composite=True)
