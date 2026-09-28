# Reglas del mus (Mus Arena)

Reglas oficiales que implementa el motor `musarena`. Si una regla cambia, se cambia **aquí primero** y
después en el código y los tests.

## 1. Mesa y jugadores

- **4 jugadores** en **2 parejas**. Asientos `0, 1, 2, 3`; la pareja A son los asientos `0` y `2`,
  la pareja B los asientos `1` y `3` (los compañeros se sientan enfrente).
- El orden de turno es `0 → 1 → 2 → 3 → 0…` (sentido antihorario de la mesa real).
- **Mano**: el jugador que habla primero en cada mano. Es el siguiente al que reparte.
  Al terminar cada mano, la mano pasa al siguiente asiento. La primera mano de la partida es el
  asiento `0`, y la rotación continúa de una vaca a la siguiente.
- Cada asiento puede ocuparlo un **humano** o un **bot**; el motor no distingue entre ellos.

## 2. Baraja

- **Baraja española de 40 cartas** (estilo Fournier): palos **oros, copas, espadas y bastos**.
- Cartas por palo: `1 (As), 2, 3, 4, 5, 6, 7, 10 (Sota), 11 (Caballo), 12 (Rey)`.
- Se juega a **8 reyes**: los **treses cuentan como reyes** y los **doses como ases**
  a todos los efectos (grande, chica, pares y juego).

## 3. Reparto y fase de mus

1. Se barajan las 40 cartas y se reparten **4 cartas** a cada jugador.
2. Empezando por la mano, cada jugador dice **"mus"** o **"no hay mus"** (cortar).
3. Si **los cuatro** dicen mus, cada jugador descarta **de 1 a 4 cartas** y roba otras tantas.
   Se vuelve al paso 2.
4. Si el mazo se acaba, se barajan los **descartes** (nunca las cartas en mano) y se sigue robando.
5. En cuanto alguien corta, empiezan los lances.

## 4. Lances

Se juegan en este orden: **Grande → Chica → Pares → Juego (o Punto)**.

### Grande
Gana la mejor mano comparando carta a carta de mayor a menor.
Orden: `Rey(12 y 3) > Caballo > Sota > 7 > 6 > 5 > 4 > As(1 y 2)`.

### Chica
Igual que la grande pero al revés: gana la mano más baja comparando de menor a mayor.

### Pares
- Antes de apostar, cada jugador declara, en orden, si **tiene pares o no** (es obligatorio decir la verdad).
  Como no se puede mentir, el motor hace la declaración automáticamente y la deja en el historial público.
- Jugadas, de menor a mayor:
  - **Par**: 2 cartas iguales.
  - **Medias**: 3 cartas iguales.
  - **Duples**: dos pares, o 4 cartas iguales.
- Entre jugadas del mismo tipo gana la de cartas más altas (orden de la grande).
- Solo hay apuestas si **las dos parejas** tienen pares. Si solo una los tiene, se lleva los tantos
  sin apuesta.

### Juego
- Valor de las cartas: figuras (Sota, Caballo, Rey) y **treses** valen **10**; los **doses** valen **1**;
  el resto su número.
- Hay juego con **31 o más**. Orden de mejor a peor: `31 > 32 > 40 > 37 > 36 > 35 > 34 > 33`.
- Cada jugador declara si **tiene juego o no**. Solo hay apuestas si las dos parejas tienen juego.
- Si **nadie** tiene juego se juega al **Punto**: gana quien más se acerque a 30 (sin pasarse, al ser <31).

### Empates
En cualquier lance, **gana el jugador más cercano a la mano** (el que habla antes).

## 5. Apuestas

En cada lance hablan los jugadores por orden desde la mano. Las acciones son:

| Acción               | Cuándo                     | Efecto                                                     |
| -------------------- | -------------------------- | ---------------------------------------------------------- |
| **Paso**             | Nadie ha envidado          | No apuesta                                                 |
| **Envido**           | Nadie ha envidado          | Apuesta **2** tantos (opción por defecto)                  |
| **Envido N**         | Nadie ha envidado          | Apuesta **N** tantos, con **N entre 3 y 40**               |
| **Órdago**           | Siempre que se pueda hablar | Apuesta la vaca entera                                     |
| **Quiero**           | Hay apuesta del rival      | Se acepta la apuesta; se resuelve al final de la mano      |
| **No quiero**        | Hay apuesta del rival      | Se rechaza; el rival cobra lo que había antes (mín. 1)     |
| **Reenvido N**       | Hay apuesta del rival      | Sube la apuesta N tantos más (N entre 2 y 40)              |

- Responde la **pareja contraria**; basta con que **uno** de los dos diga "quiero". Si los dos dicen
  "no quiero", se rechaza.
- **No quiero**: la pareja que apostó cobra **1 tanto** si era la primera apuesta, o el valor de la
  apuesta anterior aceptada si era un reenvido.
- **Todos pasan** en grande o chica: el lance queda **"en paso"** y el ganador cobra **1 tanto** al final.
- **Órdago aceptado**: se muestran las cartas inmediatamente; quien gane ese lance gana **la vaca**
  y la mano termina.

Aclaraciones:

- En **pares** y **juego** solo hablan (apuestan y responden) los jugadores que **tienen** la jugada.
  En grande, chica y punto hablan los cuatro.
- Ante una apuesta, responde primero el rival **más cercano a la mano**; si dice "no quiero", habla
  su compañero.
- Los tantos de un **no quiero** se cobran **en el momento**. Si con ellos una pareja llega a 40,
  gana la vaca y la mano termina.
- A un **órdago** solo se puede responder **quiero** o **no quiero** (no se reenvida sobre él).
- Todas las apuestas se hacen con tantos enteros y el **total** de una apuesta no puede pasar de
  **40**: un reenvido solo puede subir hasta 40 menos lo que ya hay apostado. Si no cabe ni un
  reenvido de 2, solo se puede responder quiero, no quiero u órdago.

## 6. Recuento al final de la mano

Se cuenta en orden **Grande → Chica → Pares → Juego/Punto**:

- **Grande y Chica**: la apuesta aceptada, o 1 tanto si quedó en paso.
- **Pares**: la apuesta aceptada **más** el valor de los pares de **los dos jugadores** de la pareja
  ganadora: par = 1, medias = 2, duples = 3.
- **Juego**: la apuesta aceptada **más** 3 tantos por cada 31 y 2 por cualquier otro juego de
  la pareja ganadora.
- **Punto**: la apuesta aceptada **más** 1 tanto.

Si una pareja llega a **40** durante el recuento, gana la vaca en ese momento y no se sigue contando.

Aclaraciones:

- **En paso** (todos pasan): en grande y chica el ganador del lance cobra **1 tanto**; en pares y
  juego **no** hay tanto extra, solo los valores de pares o de juego de la pareja ganadora; en punto,
  el tanto del punto.
- **Sin apuesta** (en pares o juego solo una pareja tiene la jugada): esa pareja cobra sus valores
  de pares o de juego.
- **No quiero**: además del tanto (o la apuesta anterior) cobrado en el momento, en pares, juego y
  punto la pareja que envidó cobra en el recuento los valores de **sus** jugadas (sus pares, su juego
  o el tanto del punto), sin compararlas con las del rival.

## 7. Vacas y partida

- Una **vaca** se gana al llegar a **40 tantos**.
- La partida se juega **al mejor de 3 vacas** (gana quien consigue 2) o **al mejor de 5 vacas**
  (gana quien consigue 3). Se elige al crear la partida.
- Tras cada vaca, los tantos vuelven a 0.

## 8. Chat abierto

- La mesa tiene un **chat abierto**: cualquier jugador puede escribir un mensaje en cualquier momento
  y **todos** los jugadores lo ven.
- El chat **no altera** el estado del juego ni es una acción de turno. Los bots pueden leerlo o ignorarlo.

## 9. Información oculta

- Cada jugador solo ve **sus propias cartas**, nunca las de los rivales **ni las de su compañero**.
- Las cartas de los demás solo se revelan al final de la mano (o tras un órdago aceptado). Al final
  de **cada** mano los cuatro jugadores enseñan sus cartas.
