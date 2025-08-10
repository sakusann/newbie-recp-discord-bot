from flask import Flask
from threading import Thread
import time

app = Flask('')

start_time = time.time()

@app.route('/')
def home():
    uptime = time.time() - start_time
    uptime_hours = int(uptime // 3600)
    uptime_minutes = int((uptime % 3600) // 60)
    
    return f"""
    <html>
    <head><title>Discord Bot on Render</title></head>
    <body>
        <h1>🤖 Discord Bot Status</h1>
        <p><strong>Platform:</strong> Render</p>
        <p><strong>Status:</strong> <span style="color: green;">RUNNING</span></p>
        <p><strong>Uptime:</strong> {uptime_hours}時間 {uptime_minutes}分</p>
        <p><strong>Last ping:</strong> {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        <hr>
        <p>🔄 Uptime Robot monitoring active</p>
        <p>📡 <a href="/ping">Ping endpoint</a></p>
    </body>
    </html>
    """

@app.route('/ping')
def ping():
    return "pong"

@app.route('/health')
def health():
    return {
        "status": "healthy",
        "uptime_seconds": time.time() - start_time,
        "platform": "render",
        "timestamp": time.time()
    }

def run():
    # Renderは環境変数PORTを提供
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
    print("🌐 Keep-alive server started on Render")