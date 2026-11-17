from sqlalchemy import Numeric, Text
from sqlalchemy.dialects.mysql import LONGTEXT

Dinheiro = Numeric(15, 2)
TextoLongo = Text().with_variant(LONGTEXT(), "mysql")
