from sqlalchemy import Column, ForeignKey, Integer, String, LargeBinary, create_engine
from sqlalchemy.orm import relationship
from catalog_base import Base

class CatalogMain(Base):
    __tablename__ = 'catalog_main'
    # Here we define columns for the table person
    id = Column(Integer, primary_key=True)
    bioproject = Column(String(250), nullable=False)
    biosample = Column(String(250), nullable=False)
    bioexperiment = Column(String(250), nullable=False)


class CatalogBioExpt(Base):
    __tablename__ = 'catalog_experiment'
    # Here we define columns for the table address.
    id = Column(Integer, primary_key=True)
    biosample = Column(Integer, ForeignKey('catalog_main.biosample'))
    catalog_main = relationship(CatalogMain)


class Catalogrun(Base):
    __tablename__ = 'catalog_run'
    # Here we define columns for the table address.
    # Notice that each column is also a normal Python instance attribute.
    id = Column(Integer, primary_key=True)
    run = Column(String(250), nullable=True)
    biosample = Column(Integer, ForeignKey('catalog_main.biosample'))
    bioexperiment = Column(String(250), ForeignKey('catalog_main.bioexperiment'))
    catalog_main = relationship(CatalogMain)


class CatalogChkpoint(Base):
    __tablename__ = 'catalog_checkpoint'
    id = Column(Integer, primary_key=True)
    chkpoint = Column(String(250), nullable=True)
    value = Column(LargeBinary, nullable=True)
    run = Column(String(250), ForeignKey('catalog_run.run'))
    catalog_run = relationship(Catalogrun)

class CatalogRunParams(Base):
    __tablename__ = 'catalog_run_parms'
    id = Column(Integer, primary_key=True)
    run = Column(String(250), ForeignKey('catalog_run.run'))
    program = Column(String(250),nullable=True)
    parms = Column(String(250),nullable=True)
    time_elapsed = Column(String(250),nullable=True)
    memory_used = Column(String(250), nullable=True)
    swap_used = Column(String(250), nullable=True)
    catalog_run = relationship(Catalogrun)


# Create an engine that stores data in the local directory's
# sqlalchemy_example.db file.
#engine = create_engine('sqlite:///:memory:', echo=True)

# Create all tables in the engine. This is equivalent to "Create Table"
# statements in raw SQL.

