"""로컬 개발 서버 — Vercel 배포 전 테스트용"""
from flask import Flask, send_file, request, jsonify
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))
from chart import process  # api/chart.py 재사용
from urllib.parse import parse_qs

app = Flask(__name__)


@app.route('/')
def index():
    return send_file('index.html')


@app.route('/api/chart')
def chart_data():
    params = {k: [v] for k, v in request.args.items()}
    result, status = process(params)
    return jsonify(result), status


if __name__ == '__main__':
    app.run(debug=True, port=5050)
