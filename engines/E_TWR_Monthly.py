#!/usr/bin/env python3
"""
engines/E_TWR_Monthly.py — TWR Mensal com Método da Cota

Calcula a rentabilidade mensal do portfólio de ações usando Time-Weighted Return
(TWR) com o método da cota, idêntico ao usado por fundos de investimento
brasileiros.

Metodologia:
    1. Cada dia, a "cota" do portfólio muda apenas por variação de mercado.
    2. Compras/vendas alteram o número de cotas, NÃO o valor da cota.
    3. r_diário = (V_t - CF_t) / V_{t-1} - 1
    4. r_mensal = ∏(1 + r_diário) - 1  (encadeamento dos retornos diários)
    5. r_acumulado = ∏(1 + r_mensal) - 1

Caixa parado (não investido em ativos) é EXCLUÍDO do cálculo.

Duas interfaces disponíveis:
    1. calcular_rentabilidade_mensal()   — função standalone com dados genéricos
    2. compute_monthly_twr_from_daily()  — usa série diária pré-calculada (D_Publish)

Usage:
    # Standalone
    from engines.E_TWR_Monthly import calcular_rentabilidade_mensal
    resultado = calcular_rentabilidade_mensal(transacoes, precos, extrato, inicio, fim)

    # Via D_Publish
    from engines.E_TWR_Monthly import compute_monthly_twr_from_daily
    resultado = compute_monthly_twr_from_daily(daily_df)
"""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════════════════════
# FUNÇÃO 1: STANDALONE — Dados genéricos (assinatura pedida pelo usuário)
# ═══════════════════════════════════════════════════════════════════════════════


def calcular_rentabilidade_mensal(
    transacoes: List[dict],
    precos_fechamento: dict,
    extrato: List[dict],
    data_inicio: str,
    data_fim: str,
) -> dict:
    """
    Calcula a rentabilidade mensal TWR do portfólio de ações.

    Metodologia (TWR mensal com cota):
        1. Reconstrói as posições dia a dia a partir das transações
        2. Calcula o valor de mercado no fim de cada mês (precos_fechamento)
        3. Identifica fluxos líquidos em ativos por mês (custo compras - receita vendas)
        4. r_mes = V_final / (V_inicial + Fluxos) - 1
        5. Encadeia multiplicativamente: TWR = ∏(1 + r_i) - 1

    Premissas:
        - Meses sem posição em ativos retornam 0%
        - Fluxos entram na base de cálculo do mês em que ocorrem
        - Direitos de subscrição são tratados como ativo separado
        - Custos de corretagem estão incluídos em custos_alocados e
          são incorporados ao preço médio de compra
        - Caixa parado (não investido) é excluído do cálculo

    Args:
        transacoes: lista de dicts, cada um com:
            - data (str "YYYY-MM-DD")
            - acao (str, código do ativo, ex: "CSMG3")
            - operacao (str, "C" para compra, "V" para venda)
            - quantidade (int/float)
            - preco_unitario (float)
            - valor_total (float, = quantidade × preco_unitario)
            - nota_corretagem (str, número da nota)
            - custos_alocados (float, taxa liq. + emolumentos alocados)

        precos_fechamento: dict {acao: {data_str: preco_float}}
            Preços de fechamento por ação e data. Idealmente inclui
            o último dia útil de cada mês.

        extrato: lista de dicts com:
            - data (str "YYYY-MM-DD")
            - tipo (str, "Deposito" ou "Resgate")
            - valor (float)
            Nota: o extrato NÃO é usado no cálculo TWR stock-only.
            É aceito na assinatura para compatibilidade e referência.

        data_inicio: str "YYYY-MM-DD" — início do período
        data_fim: str "YYYY-MM-DD" — fim do período

    Returns:
        dict com:
            meses: lista de dicts por mês com:
                mes, valor_inicial, fluxos, valor_final,
                retorno_mes, retorno_acumulado, fator_acumulado
            twr_total: float — retorno TWR acumulado
            periodo: dict {inicio, fim} — meses extremos
    """
    # ── Etapa 1: Ordenar transações por data ──
    txns = sorted(transacoes, key=lambda t: t["data"])

    # ── Etapa 2: Construir range de meses ──
    dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
    dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
    months = pd.period_range(
        start=pd.Period(dt_inicio, freq="M"),
        end=pd.Period(dt_fim, freq="M"),
        freq="M",
    )

    # ── Etapa 3: Iterar por mês, calcular retornos ──
    posicoes: Dict[str, float] = defaultdict(float)  # acao -> quantidade
    valor_inicial = 0.0
    fator_acumulado = 1.0
    resultados = []

    for month in months:
        month_str = str(month)  # "YYYY-MM"

        # 3a. Filtrar transações do mês corrente
        txns_mes = [t for t in txns if t["data"][:7] == month_str]

        # 3b. Calcular fluxos líquidos (capital que entra/sai do portfólio de ações)
        #     Compra: fluxo POSITIVO (capital entra → mais ações)
        #     Venda: fluxo NEGATIVO (capital sai → menos ações)
        fluxos = 0.0
        total_sell_proceeds = 0.0  # rastrear vendas separadamente
        had_sells = False

        for t in txns_mes:
            custo_total = t.get("valor_total", 0.0) + t.get("custos_alocados", 0.0)
            if t["operacao"] == "C":
                # Compra: incrementa posição, capital ENTRA no portfólio
                posicoes[t["acao"]] += t["quantidade"]
                fluxos += custo_total
            elif t["operacao"] == "V":
                # Venda: decrementa posição, capital SAI do portfólio
                posicoes[t["acao"]] -= t["quantidade"]
                receita = t.get("valor_total", 0.0) - t.get("custos_alocados", 0.0)
                fluxos -= receita
                total_sell_proceeds += receita
                had_sells = True

        # 3c. Limpar posições zeradas ou negativas (arredondamento)
        posicoes = defaultdict(
            float,
            {k: v for k, v in posicoes.items() if v > 0.001},
        )

        # 3d. Calcular valor final usando precos_fechamento
        #     Encontra o último preço disponível dentro do mês para cada ação
        valor_final = 0.0
        for acao, qty in posicoes.items():
            preco = _encontrar_preco_mes(precos_fechamento.get(acao, {}), month_str)
            if preco is not None:
                valor_final += qty * preco

        # ── Etapa 4: Calcular retorno do mês ──
        #
        # Fórmula base: r = V_final / (V_inicial + Fluxos) - 1
        #
        # Casos especiais:
        #   a) Sem posições o mês inteiro (V_inicio=0, V_final=0, sem trades) → 0%
        #   b) Liquidação total (V_final=0, houve vendas):
        #      Usar sell_proceeds como "valor realizado"
        #      r = (sell_proceeds) / (V_inicio + buy_cost) - 1
        #   c) Denominador muito pequeno → 0% (evitar divisão por ~zero)
        denominador = valor_inicial + fluxos

        if not txns_mes and valor_final < 0.01 and valor_inicial < 0.01:
            # Caso a: mês completamente vazio
            retorno_mes = 0.0
        elif valor_final < 0.01 and had_sells and valor_inicial > 0.01:
            # Caso b: liquidação total — o portfólio foi vendido
            # Computar como: r = total_realizado / capital_investido - 1
            buy_cost = sum(
                t["valor_total"] + t.get("custos_alocados", 0.0)
                for t in txns_mes
                if t["operacao"] == "C"
            )
            capital_investido = valor_inicial + buy_cost
            if capital_investido > 0.01:
                retorno_mes = total_sell_proceeds / capital_investido - 1
            else:
                retorno_mes = 0.0
        elif abs(denominador) < 0.01:
            # Caso c: denominador ~zero
            retorno_mes = 0.0
        else:
            # Caso normal
            retorno_mes = valor_final / denominador - 1

        # ── Etapa 5: Encadear retornos ──
        fator_acumulado *= (1 + retorno_mes)
        retorno_acumulado = fator_acumulado - 1

        resultados.append({
            "mes": month_str,
            "valor_inicial": round(valor_inicial, 2),
            "fluxos": round(fluxos, 2),
            "valor_final": round(valor_final, 2),
            "retorno_mes": round(retorno_mes, 6),
            "retorno_acumulado": round(retorno_acumulado, 6),
            "fator_acumulado": round(fator_acumulado, 6),
        })

        # Próximo mês: valor inicial = valor final deste mês
        valor_inicial = valor_final

    # ── Etapa 6: Resultado final ──
    twr_total = fator_acumulado - 1

    return {
        "meses": resultados,
        "twr_total": round(twr_total, 6),
        "periodo": {
            "inicio": str(months[0]) if len(months) > 0 else data_inicio[:7],
            "fim": str(months[-1]) if len(months) > 0 else data_fim[:7],
        },
    }


def _encontrar_preco_mes(precos: dict, month_str: str) -> Optional[float]:
    """Encontra o preço de fechamento do último dia disponível no mês.

    Busca todas as datas em `precos` que pertencem ao mês `month_str`
    e retorna o preço da data mais recente.

    Args:
        precos: dict {data_str: preco_float}
        month_str: "YYYY-MM"

    Returns:
        float ou None se nenhum preço encontrado no mês
    """
    matching = [
        (dt, p) for dt, p in precos.items()
        if dt[:7] == month_str
    ]
    if not matching:
        return None
    matching.sort(key=lambda x: x[0], reverse=True)
    return matching[0][1]


# ═══════════════════════════════════════════════════════════════════════════════
# FUNÇÃO 2: INTEGRAÇÃO D_PUBLISH — Usa série diária pré-calculada
# ═══════════════════════════════════════════════════════════════════════════════


def compute_monthly_twr_from_daily(daily_df: pd.DataFrame) -> dict:
    """
    Agrega retornos diários TWR por mês e encadeia.

    Usa a série diária já calculada por D_Publish._build_real_daily_series()
    (portfolio_real_daily.csv) que contém retornos TWR diários exatos.

    Metodologia:
        1. Agrupa os retornos diários por mês (YYYY-MM)
        2. Encadeia dentro de cada mês: r_mes = ∏(1 + r_dia) - 1
        3. Detecta meses-gap (sem dados) e atribui 0%
        4. Encadeia os meses: TWR_total = ∏(1 + r_mes) - 1
        5. Calcula CDI mensal em paralelo para comparação

    Vantagem sobre a fórmula simplificada:
        - Exato: usa os retornos diários TWR já ajustados por fluxos
        - Trata corretamente meses com liquidação total (Nov/25)
        - Trata corretamente transições com gap (Nov→Jan)

    Args:
        daily_df: DataFrame com colunas:
            date, portfolio_value, cost_basis, cash_flow,
            portfolio_return, benchmark_return, cdi_return

    Returns:
        dict com:
            method: str — identificador do método
            meses: list[dict] — breakdown mensal
            twr_total: float — retorno TWR acumulado
            cdi_total: float — CDI acumulado no mesmo período
            periodo: dict {inicio, fim}
    """
    if daily_df is None or daily_df.empty:
        return {}

    # ── Preparar dados ──
    df = daily_df.copy()
    df["date_dt"] = pd.to_datetime(df["date"])
    df["month"] = df["date_dt"].dt.to_period("M")
    df["port_r"] = pd.to_numeric(df["portfolio_return"], errors="coerce")
    df["pv"] = pd.to_numeric(df["portfolio_value"], errors="coerce")
    df["cf"] = pd.to_numeric(df["cash_flow"], errors="coerce").fillna(0)
    df["cdi_r"] = pd.to_numeric(df["cdi_return"], errors="coerce")

    # ── Range completo de meses (incluindo gaps como Dez/25) ──
    first_month = df["month"].min()
    last_month = df["month"].max()
    all_months = pd.period_range(start=first_month, end=last_month, freq="M")

    # ── Iterar por mês ──
    fator_acumulado = 1.0
    fator_cdi_acum = 1.0
    meses: List[dict] = []

    for month in all_months:
        month_str = str(month)  # "YYYY-MM"
        month_data = df[df["month"] == month]

        if month_data.empty:
            # ── Mês-gap: sem posições ──
            # Ex: Dez/25 — portfólio foi totalmente liquidado em Nov
            # Retorno = 0% (sem capital at risk)
            retorno_mes = 0.0
            retorno_cdi = 0.0
            valor_inicial = 0.0
            valor_final = 0.0
            fluxos = 0.0
            pregoes = 0
        else:
            # ── Mês com dados ──
            # Encadear retornos diários dentro do mês
            daily_returns = month_data["port_r"].dropna()
            if daily_returns.empty:
                retorno_mes = 0.0
            else:
                retorno_mes = float(np.prod(1 + daily_returns.values) - 1)

            # CDI mensal (mesma lógica de encadeamento)
            cdi_rets = month_data["cdi_r"].dropna()
            retorno_cdi = (
                float(np.prod(1 + cdi_rets.values) - 1)
                if not cdi_rets.empty
                else 0.0
            )

            # Valores para display
            valor_inicial = float(month_data["pv"].iloc[0])
            valor_final = float(month_data["pv"].iloc[-1])
            fluxos = float(month_data["cf"].sum())
            pregoes = len(month_data)

        # ── Encadear ──
        fator_acumulado *= (1 + retorno_mes)
        fator_cdi_acum *= (1 + retorno_cdi)
        retorno_acumulado = fator_acumulado - 1

        meses.append({
            "mes": month_str,
            "valor_inicial": round(valor_inicial, 2),
            "fluxos": round(fluxos, 2),
            "valor_final": round(valor_final, 2),
            "retorno_mes": round(retorno_mes, 6),
            "retorno_cdi": round(retorno_cdi, 6),
            "retorno_acumulado": round(retorno_acumulado, 6),
            "fator_acumulado": round(fator_acumulado, 6),
            "pregoes": pregoes,
        })

    # ── Totais ──
    twr_total = fator_acumulado - 1
    cdi_total = fator_cdi_acum - 1

    return {
        "method": "twr_monthly_quota",
        "meses": meses,
        "twr_total": round(twr_total, 6),
        "cdi_total": round(cdi_total, 6),
        "periodo": {
            "inicio": str(all_months[0]) if len(all_months) > 0 else "",
            "fim": str(all_months[-1]) if len(all_months) > 0 else "",
        },
    }

