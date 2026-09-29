import random
from collections import Counter

from musarena.cards import Baraja, Carta, Palo, ordenar_cartas, todas_las_cartas


def test_baraja_tiene_40_cartas_distintas():
    cartas = todas_las_cartas()
    assert len(cartas) == 40
    assert len(set(cartas)) == 40
    assert Counter(c.palo for c in cartas) == {palo: 10 for palo in Palo}


def test_no_hay_ochos_ni_nueves():
    assert {c.numero for c in todas_las_cartas()} == {1, 2, 3, 4, 5, 6, 7, 10, 11, 12}


def test_ocho_reyes_y_ocho_ases():
    rangos = Counter(c.rango for c in todas_las_cartas())
    assert rangos[12] == 8
    assert rangos[1] == 8
    assert 2 not in rangos and 3 not in rangos


def test_nombres_de_cartas():
    assert str(Carta(12, Palo.OROS)) == "Rey de oros"
    assert str(Carta(11, Palo.COPAS)) == "Caballo de copas"
    assert str(Carta(10, Palo.ESPADAS)) == "Sota de espadas"
    assert str(Carta(1, Palo.BASTOS)) == "As de bastos"


def test_ordenar_de_mayor_a_menor_segun_la_grande():
    cartas = [
        Carta(1, Palo.OROS), Carta(3, Palo.COPAS), Carta(7, Palo.OROS), Carta(12, Palo.BASTOS),
        Carta(2, Palo.ESPADAS), Carta(11, Palo.OROS), Carta(10, Palo.COPAS), Carta(4, Palo.OROS),
    ]
    assert [c.numero for c in ordenar_cartas(cartas)] == [12, 3, 11, 10, 7, 4, 2, 1]


def test_ordenar_cartas_iguales_por_palo():
    reyes = [Carta(12, Palo.BASTOS), Carta(12, Palo.OROS), Carta(3, Palo.COPAS)]
    assert ordenar_cartas(reyes) == [Carta(12, Palo.OROS), Carta(12, Palo.BASTOS),
                                     Carta(3, Palo.COPAS)]


def test_barajar_es_reproducible_con_semilla():
    a = Baraja(random.Random(7)).robar(10)
    b = Baraja(random.Random(7)).robar(10)
    c = Baraja(random.Random(8)).robar(10)
    assert a == b
    assert a != c


def test_robar_rebaraja_los_descartes_cuando_se_acaba_el_mazo():
    baraja = Baraja(random.Random(1))
    primeras = baraja.robar(40)
    assert baraja.mazo == []
    baraja.descartar(primeras[:3])
    otra = baraja.robar(2)
    assert set(otra) <= set(primeras[:3])
    assert len(baraja.descartes) == 0 and len(baraja.mazo) == 1
