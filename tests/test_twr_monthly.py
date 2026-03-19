#!/usr/bin/env python3
"""
tests/test_twr_monthly.py — Testes unitários para E_TWR_Monthly

Cobertura:
    1. Mês sem posição → retorno 0%
    2. Mês com aporte (compra) → retorno correto
    3. Mês com resgate (venda) → retorno correto
    4. Encadeamento correto de múltiplos meses
    5. Liquidação total → retorno correto (não -100%)
    6. compute_monthly_twr_from_daily() — aggregation de retornos diários

Execução:
    cd /Users/gabrielcampos/PortfolioESG
    python3 -m pytest tests/test_twr_monthly.py -v
    # ou
    python3 -m unittest tests.test_twr_monthly -v
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engines.E_TWR_Monthly import (
    calcular_rentabilidade_mensal,
    compute_monthly_twr_from_daily,
)


class TestCalcularRentabilidadeMensal(unittest.TestCase):
    """Testes para a função standalone calcular_rentabilidade_mensal()."""

    def test_mes_sem_posicao(self):
        """Mês sem transações e sem posições → retorno 0%."""
        transacoes = []
        precos = {}
        extrato = []

        resultado = calcular_rentabilidade_mensal(
            transacoes, precos, extrato,
            "2025-12-01", "2025-12-31",
        )

        self.assertEqual(len(resultado["meses"]), 1)
        self.assertAlmostEqual(resultado["meses"][0]["retorno_mes"], 0.0)
        self.assertAlmostEqual(resultado["twr_total"], 0.0)

    def test_mes_com_aporte(self):
        """Mês com compra de ações → retorno baseado em valorização."""
        # Comprar 10 STOCK1 a R$100 no dia 5
        # Preço no fim do mês: R$110
        # Retorno esperado: 1100 / 1000 - 1 = +10%
        transacoes = [
            {
                "data": "2025-01-05",
                "acao": "STOCK1",
                "operacao": "C",
                "quantidade": 10,
                "preco_unitario": 100.0,
                "valor_total": 1000.0,
                "nota_corretagem": "001",
                "custos_alocados": 0.0,
            },
        ]
        precos = {
            "STOCK1": {"2025-01-31": 110.0},
        }
        extrato = [
            {"data": "2025-01-04", "tipo": "Deposito", "valor": 1000.0},
        ]

        resultado = calcular_rentabilidade_mensal(
            transacoes, precos, extrato,
            "2025-01-01", "2025-01-31",
        )

        self.assertEqual(len(resultado["meses"]), 1)
        mes = resultado["meses"][0]
        self.assertEqual(mes["mes"], "2025-01")
        self.assertAlmostEqual(mes["valor_inicial"], 0.0)
        self.assertAlmostEqual(mes["valor_final"], 1100.0)
        self.assertAlmostEqual(mes["retorno_mes"], 0.10, places=4)
        self.assertAlmostEqual(resultado["twr_total"], 0.10, places=4)

    def test_mes_com_resgate(self):
        """Mês com venda parcial → retorno reflete valorização."""
        # Posição inicial: 20 STOCK1 a R$100 (V_inicio = 2000)
        # Compra 20 em Jan, preço sobe, vende 10 em Fev a R$115, fim em R$120
        # Fev: V_inicio = 2400 (20 * 120), sell 10 at 115 = 1150
        # Remaining: 10 * R$120 = 1200
        # Fluxos = -1150 (sell)
        # r = 1200 / (2400 - 1150) - 1 = 1200/1250 - 1 = -4%

        # Mês 1: compra
        transacoes = [
            {
                "data": "2025-01-05",
                "acao": "STOCK1",
                "operacao": "C",
                "quantidade": 20,
                "preco_unitario": 100.0,
                "valor_total": 2000.0,
                "nota_corretagem": "001",
                "custos_alocados": 0.0,
            },
            {
                "data": "2025-02-10",
                "acao": "STOCK1",
                "operacao": "V",
                "quantidade": 10,
                "preco_unitario": 115.0,
                "valor_total": 1150.0,
                "nota_corretagem": "002",
                "custos_alocados": 0.0,
            },
        ]
        precos = {
            "STOCK1": {
                "2025-01-31": 120.0,
                "2025-02-28": 120.0,
            },
        }
        extrato = []

        resultado = calcular_rentabilidade_mensal(
            transacoes, precos, extrato,
            "2025-01-01", "2025-02-28",
        )

        self.assertEqual(len(resultado["meses"]), 2)

        # Jan: r = 2400 / (0 + 2000) - 1 = +20%
        jan = resultado["meses"][0]
        self.assertAlmostEqual(jan["retorno_mes"], 0.20, places=4)

        # Fev: V_inicio=2400, sell 10@115=1150, remaining 10@120=1200
        # fluxos = -1150, denominador = 2400 - 1150 = 1250
        # r = 1200 / 1250 - 1 = -4%
        fev = resultado["meses"][1]
        self.assertAlmostEqual(fev["retorno_mes"], -0.04, places=4)

    def test_encadeamento_correto(self):
        """Verificar que o encadeamento multiplicativo é correto."""
        transacoes = [
            {
                "data": "2025-01-05",
                "acao": "STOCK1",
                "operacao": "C",
                "quantidade": 10,
                "preco_unitario": 100.0,
                "valor_total": 1000.0,
                "nota_corretagem": "001",
                "custos_alocados": 0.0,
            },
        ]
        precos = {
            "STOCK1": {
                "2025-01-31": 110.0,   # +10%
                "2025-02-28": 110.0,   # 0% (mês vazio, mesma posição)
                "2025-03-31": 121.0,   # +10%
            },
        }
        extrato = []

        resultado = calcular_rentabilidade_mensal(
            transacoes, precos, extrato,
            "2025-01-01", "2025-03-31",
        )

        self.assertEqual(len(resultado["meses"]), 3)

        # Jan: +10%
        self.assertAlmostEqual(resultado["meses"][0]["retorno_mes"], 0.10, places=4)
        # Fev: 0% (1100→1100)
        self.assertAlmostEqual(resultado["meses"][1]["retorno_mes"], 0.0, places=4)
        # Mar: +10% (1100→1210)
        self.assertAlmostEqual(resultado["meses"][2]["retorno_mes"], 0.10, places=4)

        # Acumulado: (1.10)(1.00)(1.10) - 1 = 0.21
        self.assertAlmostEqual(resultado["twr_total"], 0.21, places=4)

        # Verificar fator_acumulado
        self.assertAlmostEqual(
            resultado["meses"][2]["fator_acumulado"], 1.21, places=4
        )

    def test_liquidacao_total(self):
        """Liquidação total (vende tudo) → retorno não é -100%."""
        transacoes = [
            # Compra em jan
            {
                "data": "2025-01-05",
                "acao": "STOCK1",
                "operacao": "C",
                "quantidade": 10,
                "preco_unitario": 100.0,
                "valor_total": 1000.0,
                "nota_corretagem": "001",
                "custos_alocados": 0.0,
            },
            # Vende tudo em fev a R$105 (ganho de 5%)
            {
                "data": "2025-02-10",
                "acao": "STOCK1",
                "operacao": "V",
                "quantidade": 10,
                "preco_unitario": 105.0,
                "valor_total": 1050.0,
                "nota_corretagem": "002",
                "custos_alocados": 0.0,
            },
        ]
        precos = {
            "STOCK1": {
                "2025-01-31": 110.0,
                "2025-02-28": 108.0,  # preço no fim do mês (não importa, posição=0)
            },
        }
        extrato = []

        resultado = calcular_rentabilidade_mensal(
            transacoes, precos, extrato,
            "2025-01-01", "2025-03-31",
        )

        # Jan: r = 1100/(0+1000) - 1 = +10%
        self.assertAlmostEqual(resultado["meses"][0]["retorno_mes"], 0.10, places=4)

        # Fev: liquidação total
        # V_inicio = 1100, vende 10@105=1050, V_final=0
        # Tratamento especial: r = sell_proceeds / (V_inicio + buy_cost)
        # r = 1050 / (1100 + 0) - 1 = -4.55%
        fev = resultado["meses"][1]
        # V_inicio=1100, sell 10@105=1050, V_final=0
        # Tratamento liquidação: r = sell_proceeds / V_inicio - 1
        # r = 1050/1100 - 1 = -4.55%
        expected_fev = 1050.0 / 1100.0 - 1  # ~ -0.04545
        self.assertAlmostEqual(fev["retorno_mes"], expected_fev,
                               places=4, msg="Liquidação deve ser ~ -4.55%")
        # Confirmar que NÃO é -100%
        self.assertGreater(fev["retorno_mes"], -0.50)

        # Mar: sem posição → 0%
        self.assertAlmostEqual(resultado["meses"][2]["retorno_mes"], 0.0, places=4)

    def test_mes_gap_entre_posicoes(self):
        """Mês sem posição entre dois meses com posições → 0%."""
        transacoes = [
            # Compra em jan
            {
                "data": "2025-01-05",
                "acao": "STOCK1",
                "operacao": "C",
                "quantidade": 10,
                "preco_unitario": 100.0,
                "valor_total": 1000.0,
                "nota_corretagem": "001",
                "custos_alocados": 0.0,
            },
            # Vende tudo em jan
            {
                "data": "2025-01-20",
                "acao": "STOCK1",
                "operacao": "V",
                "quantidade": 10,
                "preco_unitario": 105.0,
                "valor_total": 1050.0,
                "nota_corretagem": "002",
                "custos_alocados": 0.0,
            },
            # Compra de novo em mar
            {
                "data": "2025-03-05",
                "acao": "STOCK1",
                "operacao": "C",
                "quantidade": 10,
                "preco_unitario": 100.0,
                "valor_total": 1000.0,
                "nota_corretagem": "003",
                "custos_alocados": 0.0,
            },
        ]
        precos = {
            "STOCK1": {
                "2025-01-31": 108.0,
                "2025-03-31": 112.0,
            },
        }
        extrato = []

        resultado = calcular_rentabilidade_mensal(
            transacoes, precos, extrato,
            "2025-01-01", "2025-03-31",
        )

        # Jan: liquidação → retorno baseado em sell proceeds
        # Fev: gap → 0%
        self.assertAlmostEqual(resultado["meses"][1]["retorno_mes"], 0.0, places=6)
        # Mar: nova posição → retorno normal
        self.assertAlmostEqual(
            resultado["meses"][2]["retorno_mes"], 0.12, places=4,
        )  # 1120/1000 - 1 = 12%

    def test_custos_alocados(self):
        """Custos de corretagem são incluídos no fluxo (aumentam custo)."""
        transacoes = [
            {
                "data": "2025-01-05",
                "acao": "STOCK1",
                "operacao": "C",
                "quantidade": 10,
                "preco_unitario": 100.0,
                "valor_total": 1000.0,
                "nota_corretagem": "001",
                "custos_alocados": 5.0,  # R$5 de custos
            },
        ]
        precos = {"STOCK1": {"2025-01-31": 110.0}}
        extrato = []

        resultado = calcular_rentabilidade_mensal(
            transacoes, precos, extrato,
            "2025-01-01", "2025-01-31",
        )

        # Fluxo = 1000 + 5 = 1005 (custo total incluindo taxas)
        # r = 1100 / 1005 - 1 = 9.45% (menor que 10% por causa das taxas)
        mes = resultado["meses"][0]
        self.assertAlmostEqual(mes["fluxos"], 1005.0, places=2)
        expected_return = 1100.0 / 1005.0 - 1
        self.assertAlmostEqual(mes["retorno_mes"], expected_return, places=4)


class TestComputeMonthlyTwrFromDaily(unittest.TestCase):
    """Testes para compute_monthly_twr_from_daily() com DataFrame diário."""

    def _make_daily_df(self, rows: list) -> pd.DataFrame:
        """Helper para criar DataFrame no formato portfolio_real_daily.csv."""
        return pd.DataFrame(rows, columns=[
            "date", "portfolio_value", "cost_basis", "cash_flow",
            "portfolio_return", "benchmark_return", "cdi_return",
        ])

    def test_empty_df(self):
        """DataFrame vazio → resultado vazio."""
        df = pd.DataFrame()
        result = compute_monthly_twr_from_daily(df)
        self.assertEqual(result, {})

    def test_single_month(self):
        """Um mês com retornos diários → encadeamento correto."""
        # 3 dias: +5%, -2%, +3%
        # Acumulado: (1.05)(0.98)(1.03) = 1.05994 → +5.994%
        rows = [
            ["2025-01-02", 1000, 1000, 1000, "", "", ""],
            ["2025-01-03", 1050, 1000, 0, 0.05, 0.01, 0.0004],
            ["2025-01-06", 1029, 1000, 0, -0.02, -0.005, 0.0004],
            ["2025-01-07", 1059.87, 1000, 0, 0.03, 0.008, 0.0004],
        ]
        df = self._make_daily_df(rows)
        result = compute_monthly_twr_from_daily(df)

        self.assertEqual(len(result["meses"]), 1)
        expected = (1.05) * (0.98) * (1.03) - 1  # ~0.05994
        self.assertAlmostEqual(result["meses"][0]["retorno_mes"], expected, places=5)
        self.assertAlmostEqual(result["twr_total"], expected, places=5)

    def test_gap_month(self):
        """Mês-gap (sem dados) → retorno 0% sem quebrar encadeamento."""
        # Jan: dados, Fev: gap, Mar: dados
        rows = [
            ["2025-01-15", 1000, 1000, 1000, "", "", ""],
            ["2025-01-16", 1050, 1000, 0, 0.05, 0.01, 0.0004],
            # Fev: sem dados (gap)
            ["2025-03-03", 1100, 1100, 1100, 0.02, 0.005, 0.0004],
            ["2025-03-04", 1133, 1100, 0, 0.03, 0.005, 0.0004],
        ]
        df = self._make_daily_df(rows)
        result = compute_monthly_twr_from_daily(df)

        self.assertEqual(len(result["meses"]), 3)
        # Jan: +5%
        self.assertAlmostEqual(result["meses"][0]["retorno_mes"], 0.05, places=5)
        # Fev: 0% (gap)
        self.assertAlmostEqual(result["meses"][1]["retorno_mes"], 0.0, places=5)
        self.assertEqual(result["meses"][1]["pregoes"], 0)
        # Mar: (1.02)(1.03) - 1 = 0.0506
        expected_mar = (1.02) * (1.03) - 1
        self.assertAlmostEqual(result["meses"][2]["retorno_mes"], expected_mar, places=5)

        # Total = (1.05)(1.00)(1.0506) - 1
        expected_total = (1.05) * (1.00) * (1 + expected_mar) - 1
        self.assertAlmostEqual(result["twr_total"], expected_total, places=5)

    def test_chaining_matches_product(self):
        """Encadeamento mensal equivale ao produto de todos os retornos diários."""
        # Two months of daily returns
        rows = [
            ["2025-01-15", 1000, 1000, 1000, "", "", ""],
            ["2025-01-16", 1020, 1000, 0, 0.02, 0.01, 0.0004],
            ["2025-01-17", 1050, 1000, 0, 0.02941, 0.01, 0.0004],
            ["2025-02-03", 1080, 1000, 0, 0.02857, 0.01, 0.0004],
            ["2025-02-04", 1100, 1000, 0, 0.01852, 0.01, 0.0004],
        ]
        df = self._make_daily_df(rows)
        result = compute_monthly_twr_from_daily(df)

        # Manual: all daily returns
        all_rets = [0.02, 0.02941, 0.02857, 0.01852]
        manual_total = 1.0
        for r in all_rets:
            manual_total *= (1 + r)
        manual_total -= 1

        self.assertAlmostEqual(result["twr_total"], manual_total, places=5)

    def test_cdi_monthly(self):
        """CDI mensal é calculado corretamente a partir dos retornos diários."""
        rows = [
            ["2025-01-15", 1000, 1000, 1000, "", "", ""],
            ["2025-01-16", 1020, 1000, 0, 0.02, 0.01, 0.0004],
            ["2025-01-17", 1050, 1000, 0, 0.03, 0.01, 0.0005],
        ]
        df = self._make_daily_df(rows)
        result = compute_monthly_twr_from_daily(df)

        expected_cdi = (1.0004) * (1.0005) - 1
        self.assertAlmostEqual(result["meses"][0]["retorno_cdi"], expected_cdi, places=6)
        self.assertAlmostEqual(result["cdi_total"], expected_cdi, places=6)

    def test_with_real_project_data(self):
        """Teste de integração: lê portfolio_real_daily.csv do projeto."""
        csv_path = ROOT / "data" / "results" / "portfolio_real_daily.csv"
        if not csv_path.exists():
            self.skipTest("portfolio_real_daily.csv not found")

        df = pd.read_csv(csv_path)
        result = compute_monthly_twr_from_daily(df)

        # Deve ter meses de Out/25 a Mar/26 (6 meses)
        self.assertGreaterEqual(len(result["meses"]), 5)

        # TWR total deve ser ~23.5% (do METRICS_REFERENCE.md)
        self.assertAlmostEqual(result["twr_total"], 0.235, delta=0.02)

        # Dez/25 deve ser um gap month com 0%
        dec = [m for m in result["meses"] if m["mes"] == "2025-12"]
        if dec:
            self.assertAlmostEqual(dec[0]["retorno_mes"], 0.0, places=6)
            self.assertEqual(dec[0]["pregoes"], 0)

        # Verificar que o encadeamento é consistente
        fator = 1.0
        for m in result["meses"]:
            fator *= (1 + m["retorno_mes"])
        self.assertAlmostEqual(fator - 1, result["twr_total"], places=5)


if __name__ == "__main__":
    unittest.main()

