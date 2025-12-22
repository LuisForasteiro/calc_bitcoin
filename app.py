from flask import Flask, render_template
from pycoingecko import CoinGeckoAPI
import os

app = Flask(__name__)
cg = CoinGeckoAPI()

@app.route('/', methods=['GET'])
def index():
    # Busca todos os preços de uma vez ao carregar a página
    try:
        price_data = cg.get_price(ids='bitcoin', vs_currencies='brl,usd,eur')
        prices = {
            'brl': price_data['bitcoin']['brl'],
            'usd': price_data['bitcoin']['usd'],
            'eur': price_data['bitcoin']['eur']
        }
    except Exception:
        prices = None
        
    return render_template('index.html', prices=prices)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)