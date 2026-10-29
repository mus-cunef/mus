import random

import pytest

from musarena.web.formato import (
    Formato,
    Resultado,
    cabezas_tras_grupos,
    clasificar,
    describir,
    enfrentamientos_liga,
    orden_cabezas,
    primera_ronda,
    repartir_grupos,
    rondas_del_cuadro,
    separar_grupos,
    tamano_cuadro,
)

# --- Formato automático: la regla del equipo ---


@pytest.mark.parametrize(("n", "tipo", "primera"), [
    (4, "eliminatoria", "Semifinales"),
    (8, "eliminatoria", "Cuartos de final"),
    (16, "eliminatoria", "Octavos de final"),
    (6, "eliminatoria", "Cuartos de final"),  # 2 pases directos
    (12, "eliminatoria", "Octavos de final"),  # 4 pases directos
    (17, "grupos", None),
    (32, "grupos", None),
])
def test_formato_automatico(n, tipo, primera):
    f = Formato().resolver(n)
    assert f.tipo == tipo
    if primera:
        assert rondas_del_cuadro(n)[0] == primera
    else:  # más de 16: grupos de 4 y pasan 2
        assert (f.tam_grupo, f.pasan_por_grupo) == (4, 2)


def test_32_parejas_hacen_8_grupos_y_octavos():
    f = Formato().resolver(32)
    grupos = repartir_grupos(range(32), f.tam_grupo, random.Random(1))
    assert len(grupos) == 8 and all(len(g) == 4 for g in grupos)
    assert rondas_del_cuadro(len(grupos) * f.pasan_por_grupo)[0] == "Octavos de final"


def test_validar_rechaza_formatos_imposibles():
    for malo in (Formato(tipo="x"), Formato(max_parejas=1), Formato(max_parejas=65),
                 Formato(tam_grupo=2), Formato(pasan_por_grupo=4, tam_grupo=4),
                 Formato(mejor_de=4), Formato(mejor_de_final=1)):
        with pytest.raises(ValueError):
            malo.validar()
    Formato(tipo="grupos", max_parejas=40, tam_grupo=5, pasan_por_grupo=3).validar()


def test_grupos_que_no_dejan_pasar_a_nadie_se_ajustan():
    # 5 parejas en grupos de 4: 2 grupos (3 y 2), pasan como mucho 1 de cada uno.
    f = Formato(tipo="grupos", tam_grupo=4, pasan_por_grupo=3).resolver(5)
    assert f.tipo == "grupos" and f.pasan_por_grupo == 1
    # Un solo grupo de 2 del que solo podría pasar 1: se juega como liga.
    assert Formato(tipo="grupos").resolver(2).tipo == "liga"


def test_desde_dict_ignora_claves_desconocidas():
    f = Formato(tipo="liga", max_parejas=6)
    assert Formato.desde_dict({**f.a_dict(), "otra": 1}) == f


# --- Cuadro ---


def test_cabezas_de_serie_clasicas():
    assert orden_cabezas(2) == [1, 2]
    assert orden_cabezas(4) == [1, 4, 2, 3]
    assert orden_cabezas(8) == [1, 8, 4, 5, 2, 7, 3, 6]
    for tamano in (16, 32, 64):
        orden = orden_cabezas(tamano)
        assert sorted(orden) == list(range(1, tamano + 1))
        # Cada partido suma lo mismo: el mejor contra el peor, etc.
        assert {orden[i] + orden[i + 1] for i in range(0, tamano, 2)} == {tamano + 1}
        # El 1 y el 2 están en mitades distintas: solo se cruzan en la final.
        assert (orden.index(1) < tamano // 2) != (orden.index(2) < tamano // 2)


@pytest.mark.parametrize("n", range(2, 65))
def test_pases_directos_para_las_mejores_cabezas(n):
    cabezas = list(range(1, n + 1))  # 1 es la mejor
    partidos = primera_ronda(cabezas)
    tamano = tamano_cuadro(n)
    assert len(partidos) == tamano // 2
    con_pase = [a or b for a, b in partidos if a is None or b is None]
    assert sorted(con_pase) == list(range(1, tamano - n + 1))  # los mejores pasan solos
    assert all(not (a is None and b is None) for a, b in partidos)  # nunca un partido vacío
    jugando = [x for par in partidos for x in par if x is not None]
    assert sorted(jugando) == cabezas


def test_separar_grupos_evita_cruces_del_mismo_grupo():
    # 4 grupos, pasan 2: ocho clasificados. Los segundos van del 5 al 8.
    grupo_de = {"1A": 0, "1B": 1, "1C": 2, "1D": 3, "2A": 0, "2B": 1, "2C": 2, "2D": 3}
    cabezas = ["1A", "1B", "1C", "1D", "2D", "2C", "2B", "2A"]
    partidos = separar_grupos(primera_ronda(cabezas), grupo_de)
    for a, b in partidos:
        assert grupo_de[a] != grupo_de[b]
    assert sorted(x for p in partidos for x in p) == sorted(cabezas)


# --- Grupos, liga y clasificaciones ---


@pytest.mark.parametrize("n", [3, 4, 5, 8, 9])
def test_liga_todos_contra_todos_una_vez(n):
    jornadas = enfrentamientos_liga(list(range(n)))
    partidos = [frozenset(p) for j in jornadas for p in j]
    assert len(partidos) == n * (n - 1) // 2 == len(set(partidos))
    for jornada in jornadas:  # nadie juega dos veces en la misma jornada
        en_jornada = [x for p in jornada for x in p]
        assert len(en_jornada) == len(set(en_jornada))


def test_grupos_equilibrados():
    for n in range(17, 65):
        tamanos = [len(g) for g in repartir_grupos(range(n), 4, random.Random(n))]
        assert sum(tamanos) == n and max(tamanos) - min(tamanos) <= 1 and max(tamanos) <= 4


def test_clasificar_con_desempates():
    resultados = [
        Resultado("a", "b", "a", 2, 0, 80, 30),
        Resultado("c", "d", "c", 2, 1, 90, 85),
        Resultado("a", "c", "c", 1, 2, 70, 75),
        Resultado("b", "d", "d", 0, 2, 40, 80),
        Resultado("a", "d", "a", 2, 1, 85, 70),
        Resultado("b", "c", "b", 2, 1, 80, 75),
    ]
    tabla = clasificar("abcd", resultados)
    # a y c: 2 victorias; a tiene +2 vacas (5-3), c +1 (5-4) -> a primera.
    assert [f.pareja for f in tabla] == ["a", "c", "d", "b"]
    assert (tabla[0].jugados, tabla[0].ganados, tabla[0].vacas_favor) == (3, 2, 5)


def test_empate_total_lo_decide_el_partido_entre_ellas():
    # "y" y "z" quedan igual en todo (1 victoria, 3-3 en vacas, 100-100 en tantos), pero "z"
    # ganó a "y": va delante aunque "y" se inscribiera antes.
    resultados = [Resultado("y", "z", "z", 1, 2, 50, 50), Resultado("y", "x", "y", 2, 1, 50, 50),
                  Resultado("z", "x", "x", 1, 2, 50, 50)]
    tabla = clasificar("yzx", resultados)
    claves = {f.pareja: f.clave() for f in tabla}
    assert claves["y"] == claves["z"]
    assert [f.pareja for f in tabla].index("z") < [f.pareja for f in tabla].index("y")


def test_cabezas_tras_grupos_primero_los_primeros():
    t1 = clasificar("ab", [Resultado("a", "b", "a", 2, 0, 80, 10)])
    t2 = clasificar("cd", [Resultado("c", "d", "c", 2, 1, 80, 70)])
    cabezas = cabezas_tras_grupos([t1, t2], 2)
    assert [p for p, _ in cabezas] == ["a", "c", "d", "b"]  # "a" ganó con más margen
    assert dict(cabezas) == {"a": 0, "b": 0, "c": 1, "d": 1}


def test_describir():
    assert "Octavos" in describir(Formato(), 16)
    assert "4 pases directos" in describir(Formato(), 12)
    texto = describir(Formato(max_parejas=32), 32)
    assert "8 grupos de 4" in texto and "Cuadro de 16: Octavos" in texto
    assert "liga" in describir(Formato(tipo="liga"), 6)
    assert "tercer puesto" in describir(Formato(tercer_puesto=True), 8)
