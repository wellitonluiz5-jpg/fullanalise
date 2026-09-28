# =====================================================
#  AI FUTEBOL PREDICTOR — Sistema Completo
#  Extração automática de dados + Banco + Palpites
#  SEM CHAVE API | Atualização diária
# =====================================================

import requests
import pandas as pd
import time
import sqlite3
import os
from datetime import datetime
from bs4 import BeautifulSoup
import math

# ======================================
# CONFIGURAÇÕES
# ======================================
BANCO_DADOS = "futebol_dados.db"
PASTA_DADOS = "dados_extraidos"
os.makedirs(PASTA_DADOS, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"
}

# ======================================
# 💾 BANCO DE DADOS
# ======================================
def criar_banco():
    conn = sqlite3.connect(BANCO_DADOS)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS partidas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            campeonato TEXT,
            casa TEXT,
            fora TEXT,
            gols_casa INTEGER,
            gols_fora INTEGER,
            resultado TEXT,
            atualizado_em TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS times (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            campeonato TEXT,
            jogos INTEGER DEFAULT 0,
            vitorias INTEGER DEFAULT 0,
            empates INTEGER DEFAULT 0,
            derrotas INTEGER DEFAULT 0,
            gols_marcados REAL DEFAULT 0,
            gols_sofridos REAL DEFAULT 0,
            forma REAL DEFAULT 50,
            atualizado_em TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Banco de dados criado/verificado")

# ======================================
# 🌐 EXTRAÇÃO DE DADOS (football-data.co.uk)
# ======================================
def extrair_dados():
    print("\n🔄 Baixando dados...")
    
    ligas = {
        'Brasileirao_A': 'https://www.football-data.co.uk/mmz4281/2526/BRA.csv',
        'Premier_League': 'https://www.football-data.co.uk/mmz4281/2526/E0.csv',
        'La_Liga': 'https://www.football-data.co.uk/mmz4281/2526/SP1.csv',
        'Bundesliga': 'https://www.football-data.co.uk/mmz4281/2526/D1.csv',
        'Serie_A': 'https://www.football-data.co.uk/mmz4281/2526/I1.csv',
        'Ligue_1': 'https://www.football-data.co.uk/mmz4281/2526/F1.csv'
    }
    
    todas_partidas = []
    
    for nome, url in ligas.items():
        try:
            print(f"   📥 {nome}...")
            df = pd.read_csv(url)
            
            for _, linha in df.iterrows():
                if pd.notna(linha.get('Date')) and pd.notna(linha.get('HomeTeam')):
                    gc = int(linha['FTHG']) if pd.notna(linha['FTHG']) else None
                    gf = int(linha['FTAG']) if pd.notna(linha['FTAG']) else None
                    res = None
                    if gc is not None and gf is not None:
                        res = 'CASA' if gc > gf else 'FORA' if gc < gf else 'EMPATE'
                    
                    todas_partidas.append({
                        'data': linha['Date'], 'campeonato': nome,
                        'casa': linha['HomeTeam'], 'fora': linha['AwayTeam'],
                        'gols_casa': gc, 'gols_fora': gf, 'resultado': res
                    })
            
            caminho = os.path.join(PASTA_DADOS, f"{nome}.csv")
            df.to_csv(caminho, index=False, encoding='utf-8-sig')
            print(f"      ✅ Salvo — {len(df)} partidas")
            time.sleep(2)
            
        except Exception as e:
            print(f"      ⚠️ Erro: {e}")
    
    if todas_partidas:
        conn = sqlite3.connect(BANCO_DADOS)
        df_final = pd.DataFrame(todas_partidas)
        df_final['atualizado_em'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df_final.to_sql('partidas', conn, if_exists='replace', index=False)
        conn.close()
    
    return todas_partidas

# ======================================
# 📊 CALCULAR ESTATÍSTICAS
# ======================================
def calcular_estatisticas():
    print("\n📊 Calculando estatísticas dos times...")
    conn = sqlite3.connect(BANCO_DADOS)
    df = pd.read_sql("SELECT * FROM partidas", conn)
    
    if df.empty:
        print("⚠️ Sem dados ainda")
        conn.close()
        return
    
    stats = {}
    for _, jogo in df.iterrows():
        casa, fora = jogo['casa'], jogo['fora']
        gc, gf = jogo['gols_casa'], jogo['gols_fora']
        
        if pd.notna(gc) and pd.notna(gf):
            for time in [casa, fora]:
                if time not in stats:
                    stats[time] = {'jogos': 0, 'gm': 0, 'gs': 0, 'vit': 0}
            
            stats[casa]['jogos'] += 1
            stats[casa]['gm'] += gc
            stats[casa]['gs'] += gf
            if gc > gf: stats[casa]['vit'] += 1
            
            stats[fora]['jogos'] += 1
            stats[fora]['gm'] += gf
            stats[fora]['gs'] += gc
            if gf > gc: stats[fora]['vit'] += 1
    
    cursor = conn.cursor()
    for time, s in stats.items():
        mg = round(s['gm'] / max(s['jogos'], 1), 2)
        ms = round(s['gs'] / max(s['jogos'], 1), 2)
        forma = round((s['vit'] / max(s['jogos'], 1)) * 100, 1)
        
        cursor.execute('''
            INSERT OR REPLACE INTO times 
            (nome, jogos, gols_marcados, gols_sofridos, forma, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (time, s['jogos'], mg, ms, forma, 
              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    print(f"✅ {len(stats)} times atualizados")
    return stats

# ======================================
# 🧠 IA DE PREVISÃO
# ======================================
def prever_partida(time_casa, time_fora, stats):
    print(f"\n🔮 Analisando: {time_casa} vs {time_fora}")
    
    # Dados dos times
    tc = stats.get(time_casa, {'jogos': 10, 'gm': 1.5, 'gs': 1.0, 'forma': 50})
    tf = stats.get(time_fora, {'jogos': 10, 'gm': 1.3, 'gs': 1.2, 'forma': 50})
    
    # Força dos times
    fc = tc['forma'] * 0.4 + tc['gm'] * 15 - tc['gs'] * 10 + 15  # +15 fator casa
    ff = tf['forma'] * 0.4 + tf['gm'] * 15 - tf['gs'] * 10
    
    total = fc + ff
    if total == 0: total = 100
    
    prob_casa = round((fc / total) * 100, 1)
    prob_fora = round((ff / total) * 100, 1)
    prob_empate = round(100 - abs(prob_casa - prob_fora) * 0.6 - (prob_casa + prob_fora) / 2, 1)
    
    # Normalizar
    soma = prob_casa + prob_fora + prob_empate
    prob_casa = round((prob_casa / soma) * 100, 1)
    prob_fora = round((prob_fora / soma) * 100, 1)
    prob_empate = round(100 - prob_casa - prob_fora, 1)
    
    # Gols esperados (Poisson)
    gols_casa = round(tc['gm'] * (fc / 100) * (1 - tf['gs'] / 3), 1)
    gols_fora = round(tf['gm'] * (ff / 100) * (1 - tc['gs'] / 3), 1)
    placar_casa = math.floor(gols_casa + 0.5)
    placar_fora = math.floor(gols_fora + 0.5)
    total_gols = round(gols_casa + gols_fora, 1)
    escanteios = round((6.5 + tc['gm'] * 2 + tf['gm'] * 2) * 0.8)
    
    # Palpite seguro
    if prob_casa >= 62:
        seguro = f"{time_casa} ou Empate"
        risco = "Baixo 🟢"
        p_seguro = round(prob_casa + prob_empate * 0.55)
    elif prob_fora >= 62:
        seguro = f"{time_fora} ou Empate"
        risco = "Baixo 🟢"
        p_seguro = round(prob_fora + prob_empate * 0.55)
    elif total_gols < 2.2:
        seguro = "Menos de 2.5 Gols"
        risco = "Médio 🟡"
        p_seguro = 58
    else:
        seguro = "Mais de 1.5 Gols"
        risco = "Médio 🟡"
        p_seguro = 62
    
    return {
        'prob_casa': prob_casa, 'prob_empate': prob_empate, 'prob_fora': prob_fora,
        'placar': f"{placar_casa} x {placar_fora}",
        'gols_esperados': f"{gols_casa} x {gols_fora}",
        'total_gols': total_gols, 'escanteios': escanteios,
        'palpite_seguro': seguro, 'prob_segura': p_seguro, 'risco': risco
    }

# ======================================
# 🎯 EXIBIR RESULTADOS
# ======================================
def exibir_resultados(pred, tc, tf):
    print("\n" + "="*50)
    print(f"🎯 PALPITE: {tc} vs {tf}")
    print("="*50)
    print(f"📊 Probabilidades:")
    print(f"   🏠 Vitória {tc}:  {pred['prob_casa']}%")
    print(f"   🤝 Empate:        {pred['prob_empate']}%")
    print(f"   🏃 Vitória {tf}:  {pred['prob_fora']}%")
    print(f"\n⚽ Placar estimado: {pred['placar']}")
    print(f"   Gols esperados: {pred['gols_esperados']} (total: {pred['total_gols']})")
    print(f"   Escanteios: ~{pred['escanteios']}")
    print(f"\n🛡️ Palpite Menos Arriscado:")
    print(f"   ✅ {pred['palpite_seguro']} — {pred['prob_segura']}% | Risco: {pred['risco']}")
    print("="*50)
    print("⚠️  Apenas para entretenimento. Sempre há risco!")

# ======================================
# 🚀 EXECUÇÃO PRINCIPAL
# ======================================
def executar():
    print("="*50)
    print("🚀 AI FUTEBOL PREDICTOR — SISTEMA INICIADO")
    print(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("="*50)
    
    criar_banco()
    extrair_dados()
    stats = calcular_estatisticas()
    
    if not stats:
        print("\n⚠️ Sem dados suficientes para previsões")
        return
    
    # Exemplo de uso
    print("\n📋 Times disponíveis (exemplos):", ", ".join(list(stats.keys())[:8]))
    
    # === PREENCHA AQUI OS TIMES QUE QUER ANALISAR ===
    TIME_CASA = "Palmeiras"
    TIME_FORA = "Flamengo"
    # =================================================
    
    pred = prever_partida(TIME_CASA, TIME_FORA, stats)
    exibir_resultados(pred, TIME_CASA, TIME_FORA)

if __name__ == "__main__":
    executar()
