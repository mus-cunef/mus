# Partidas grabadas

Aquí se guardan solas las partidas de `mus-play` en las que juega algún humano: un archivo JSON
por partida con la semilla del reparto, el tipo de jugador de cada asiento y la lista de acciones
(ver `src/musarena/grabacion.py`). Pesan unos pocos KB.

**Se suben a GitHub** (en una PR, como el resto) para juntar las de todo el equipo: el bot
inteligente aprenderá de ellas a jugar como las personas y servirán para medirlo contra humanos.

```python
from musarena.grabacion import cargar_partidas, reproducir
for partida in cargar_partidas("partidas"):
    for decision in reproducir(partida):   # lo que vio y lo que hizo cada jugador
        ...
```

Si cambian las reglas del motor, una partida antigua puede dejar de poder reproducirse
(`reproducir` lanza `IllegalActionError`); cada archivo guarda la versión con la que se grabó.
