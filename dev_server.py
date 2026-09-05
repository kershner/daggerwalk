import asyncio
import os
import threading

from flask import Flask, jsonify, request, send_from_directory

from daggerwalk_twitch_bot import Config, DaggerfallBot


app = Flask(__name__)
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

_messages = []
_messages_lock = threading.Lock()
_loop = asyncio.new_event_loop()
_bot = None


class DevAuthor:
    name = Config.TWITCH_CHANNEL


class DevChannel:
    async def send(self, text):
        with _messages_lock:
            _messages.append(str(text))


_channel = DevChannel()


class DevMessage:
    author = DevAuthor()
    channel = _channel

    def __init__(self, content):
        self.content = content


async def _init_bot():
    global _bot
    _bot = DaggerfallBot(dev_channel=_channel)
    await _bot._start_runtime()


def _run_loop():
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(_init_bot())
    _loop.run_forever()


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "templates/dev_control.html")


@app.route("/cmd/<path:raw>")
def run_command(raw):
    if not _bot:
        return jsonify({"ok": False, "error": "bot not ready"}), 503

    content = raw.strip()
    if not content:
        return jsonify({"ok": False, "error": "empty input"}), 400
    if not content.startswith("!"):
        content = "!" + content

    try:
        message = DevMessage(content)
        future = asyncio.run_coroutine_threadsafe(_bot.event_message(message), _loop)
        future.result(timeout=60)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/chat")
def chat():
    try:
        after = max(0, int(request.args.get("after", 0)))
    except ValueError:
        after = 0

    with _messages_lock:
        messages = _messages[after:]
        cursor = len(_messages)

    return jsonify({"messages": messages, "cursor": cursor})


if __name__ == "__main__":
    import socket

    ip = socket.gethostbyname(socket.gethostname())
    port = 5050
    print("\n  Daggerwalk Dev Server running")
    print(f"  Local:   http://localhost:{port}")
    print(f"  Phone:   http://{ip}:{port}\n")

    threading.Thread(target=_run_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False)
