"""Base de datos de la web: cuentas, sesiones y torneos privados.

Las mesas normales viven en memoria (si el servidor se reinicia, se pierden), pero las cuentas
y los torneos tienen que durar. Se usa SQLAlchemy (solo el núcleo, con tablas y consultas
explícitas), así el mismo código vale para:

- **SQLite** en local y en los tests (un archivo, o la memoria con ``"sqlite://"``).
- **PostgreSQL** en internet (``MUS_BD=postgresql+psycopg://...``). El disco del servidor de
  Render se borra en cada reinicio, así que allí la base de datos tiene que ser externa.

Las fechas se guardan como segundos desde 1970 (UTC), que se comparan igual en las dos bases.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Engine,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.pool import StaticPool

metadata = MetaData()

usuarios = Table(
    "usuarios", metadata,
    Column("id", Integer, primary_key=True),
    Column("nombre", String(20), nullable=False),
    Column("nombre_clave", String(20), nullable=False, unique=True),  # en minúsculas
    Column("clave", String(200), nullable=False),  # hash scrypt, nunca la contraseña
    Column("creado", Float, nullable=False),
)

sesiones = Table(
    "sesiones", metadata,
    Column("token", String(64), primary_key=True),  # hash SHA-256 del código de la cookie
    Column("usuario", Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
    Column("expira", Float, nullable=False),
)

torneos = Table(
    "torneos_privados", metadata,
    Column("id", Integer, primary_key=True),
    Column("codigo", String(32), nullable=False, unique=True),  # va en el enlace de invitación
    Column("nombre", String(60), nullable=False),
    Column("organizador", Integer, ForeignKey("usuarios.id"), nullable=False),
    Column("formato", JSON, nullable=False),  # Formato elegido por el organizador
    Column("resuelto", JSON),  # el formato concreto al sortear (con las parejas reales)
    Column("fecha_limite", Float, nullable=False),
    Column("estado", String(12), nullable=False),  # inscripcion, en_curso, terminado, cancelado
    Column("campeon", Integer),
    Column("semilla", Integer, nullable=False),
    Column("creado", Float, nullable=False),
)

parejas = Table(
    "parejas", metadata,
    Column("id", Integer, primary_key=True),
    Column("torneo", Integer, ForeignKey("torneos_privados.id", ondelete="CASCADE"),
           nullable=False),
    Column("nombre", String(30), nullable=False),
    Column("jugador1", Integer, ForeignKey("usuarios.id"), nullable=False),  # quien la inscribe
    Column("jugador2", Integer, ForeignKey("usuarios.id"), nullable=False),  # su compañero
    Column("confirmada", Boolean, nullable=False, default=False),  # el compañero ha aceptado
    Column("grupo", Integer),
    Column("creada", Float, nullable=False),
    UniqueConstraint("torneo", "nombre"),
)

partidos = Table(
    "partidos", metadata,
    Column("id", Integer, primary_key=True),
    Column("torneo", Integer, ForeignKey("torneos_privados.id", ondelete="CASCADE"),
           nullable=False),
    Column("fase", String(10), nullable=False),  # grupos, liga, cuadro, tercero
    Column("grupo", Integer),
    Column("jornada", Integer),
    Column("ronda", Integer),  # en el cuadro: 0 es la primera ronda
    Column("posicion", Integer),  # en el cuadro: lugar dentro de la ronda
    Column("pareja_a", Integer, ForeignKey("parejas.id")),  # asientos 0 y 2
    Column("pareja_b", Integer, ForeignKey("parejas.id")),  # asientos 1 y 3
    Column("mejor_de", Integer, nullable=False),
    Column("estado", String(10), nullable=False),  # esperando, listo, jugando, terminado
    Column("ganador", Integer),
    Column("pase", Boolean, nullable=False, default=False),  # sin jugar: pase directo o w.o.
    Column("vacas_a", Integer, nullable=False, default=0),
    Column("vacas_b", Integer, nullable=False, default=0),
    Column("tantos_a", Integer, nullable=False, default=0),
    Column("tantos_b", Integer, nullable=False, default=0),
    Column("estadisticas", JSON),
    Column("semilla", Integer),
    Column("mesa", String(40)),  # id de la mesa mientras se juega
    Column("tokens", JSON),  # código de cada asiento de esa mesa
    Column("acciones", JSON),  # jugadas hechas: con la semilla, la partida se reconstruye
    Column("listos", JSON),  # usuarios que ya le han dado a "Empezar" (con los 4, se juega)
    Column("actualizado", Float),
)


def conectar(url: str) -> Engine:
    """Abre la base de datos y crea las tablas que falten."""
    if url.startswith("sqlite"):
        opciones: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            opciones["poolclass"] = StaticPool  # una sola conexión: si no, cada una es otra base
        motor = create_engine(url, **opciones)

        @event.listens_for(motor, "connect")
        def _claves_ajenas(conexion, _):
            conexion.execute("PRAGMA foreign_keys=ON")
    else:
        motor = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
    metadata.create_all(motor)
    _anadir_columnas(motor)
    return motor


def _anadir_columnas(motor: Engine) -> None:
    """Añade a una base de datos ya creada las columnas nuevas de las tablas (siempre
    opcionales), para no perder los datos al actualizar la web."""
    inspector = inspect(motor)
    with motor.begin() as c:
        for tabla in metadata.sorted_tables:
            existentes = {col["name"] for col in inspector.get_columns(tabla.name)}
            for columna in tabla.columns:
                if columna.name not in existentes and columna.nullable:
                    tipo = columna.type.compile(dialect=motor.dialect)
                    c.execute(text(f'ALTER TABLE {tabla.name} ADD COLUMN "{columna.name}" {tipo}'))
