from unittest import TestCase
from biobrewliteutils.catalog import *

def prep_db():
    pass

class TestCatalogMain(TestCase):

    def setUp(self):
        engine = create_engine('sqlite:///:memory:')

        # Create all tables in the engine. This is equivalent to "Create Table"
        # statements in raw SQL.
        Base.metadata.create_all(engine)

    def test_catalog_main(self):
        pass

