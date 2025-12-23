from flask import Flask, render_template, jsonify
import requests
import redis
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

app = Flask(__name__)

# Configuração do Redis
REDIS_URL = os.environ.get('REDIS_URL')
REDIS_HOST = os.environ.get('REDIS_HOST')
REDIS_PORT = os.environ.get('REDIS_PORT', 6379)
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD')

# Inicializar Redis com connection pooling
try:
    if REDIS_URL:
        # Se usar URL completa (Upstash ou Redis Cloud) - COM SSL
        redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            ssl_cert_reqs=None,  # Desabilita verificação SSL para Upstash
            socket_connect_timeout=10,
            socket_timeout=10,
            socket_keepalive=True,
            health_check_interval=30,
            retry_on_timeout=True,
            max_connections=10
        )
    elif REDIS_HOST:
        # Se usar host/porta separados
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=int(REDIS_PORT),
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30
        )
    else:
        # Fallback para Redis local
        redis_client = redis.Redis(
            host='localhost',
            port=6379,
            decode_responses=True,
            socket_connect_timeout=5
        )
    # Testa a conexão
    redis_client.ping()
    print("✅ Redis conectado com sucesso!")
except Exception as e:
    print(f"⚠️  Redis não disponível: {e}")
    redis_client = None

CACHE_KEY = 'rates'
CACHE_EXPIRATION = 300  # 5 minutos em segundos
COINGECKO_URL = 'https://api.coingecko.com/api/v3/exchange_rates'

# Cache em memória como fallback
memory_cache = {'rates': None, 'updatedAt': None, 'timestamp': None}

def get_rates():
    """Busca as taxas do cache Redis, memória ou da API"""
    rates = None
    updated_at = None
    
    # 1. Tenta buscar do Redis
    if redis_client:
        try:
            cached_data = redis_client.get(CACHE_KEY)
            
            if cached_data:
                data = json.loads(cached_data)
                rates = data['rates']
                updated_at = data['updatedAt']
                # Atualiza cache em memória também
                memory_cache['rates'] = rates
                memory_cache['updatedAt'] = updated_at
                memory_cache['timestamp'] = datetime.now()
                print(f"📦 Redis cache hit - Atualizado em: {updated_at}")
                return rates, updated_at
        except redis.RedisError as e:
            print(f"⚠️  Erro no Redis: {e}")
        except Exception as e:
            print(f"⚠️  Erro ao ler cache: {e}")
    
    # 2. Se não tem no Redis, verifica cache em memória (válido por 10 minutos)
    if memory_cache['rates'] and memory_cache['timestamp']:
        age = (datetime.now() - memory_cache['timestamp']).total_seconds()
        if age < 600:  # 10 minutos
            print(f"💾 Usando cache em memória ({int(age)}s atrás)")
            return memory_cache['rates'], memory_cache['updatedAt']
    
    # 3. Se não tem cache válido, busca da API
    try:
        print("🌐 Buscando dados da API CoinGecko...")
        response = requests.get(COINGECKO_URL, timeout=10)
        response.raise_for_status()
        
        api_data = response.json()
        rates = api_data['rates']
        updated_at = datetime.now().isoformat()
        
        # Salva em ambos os caches
        cache_data = {
            'rates': rates,
            'updatedAt': updated_at
        }
        
        # Salva no Redis
        if redis_client:
            try:
                redis_client.setex(
                    CACHE_KEY,
                    CACHE_EXPIRATION,
                    json.dumps(cache_data)
                )
                print(f"💾 Dados salvos no Redis (expira em {CACHE_EXPIRATION}s)")
            except Exception as e:
                print(f"⚠️  Não foi possível salvar no Redis: {e}")
        
        # Salva na memória
        memory_cache['rates'] = rates
        memory_cache['updatedAt'] = updated_at
        memory_cache['timestamp'] = datetime.now()
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            print("⚠️  Rate limit da API! Usando último cache disponível")
            # Se tiver cache em memória (mesmo expirado), usa ele
            if memory_cache['rates']:
                return memory_cache['rates'], memory_cache['updatedAt']
        print(f"❌ Erro na API: {e}")
    except Exception as e:
        print(f"❌ Erro ao buscar da API: {e}")
        # Se tiver cache em memória (mesmo expirado), usa ele
        if memory_cache['rates']:
            return memory_cache['rates'], memory_cache['updatedAt']
    
    return rates, updated_at

@app.route('/', methods=['GET'])
def index():
    # Busca todos os preços (com cache)
    rates, updated_at = get_rates()
    
    prices = None
    if rates:
        try:
            prices = {
                'brl': rates['brl']['value'],
                'usd': rates['usd']['value'],
                'eur': rates['eur']['value']
            }
        except (KeyError, TypeError):
            prices = None
        
    return render_template('index.html', prices=prices, updated_at=updated_at)

@app.route('/api/rates', methods=['GET'])
def api_rates():
    """Endpoint API que retorna as taxas com cache"""
    rates, updated_at = get_rates()
    return jsonify({
        'rates': rates,
        'updatedAt': updated_at
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)