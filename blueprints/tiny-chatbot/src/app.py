"""The world's tiniest chatbot: one Lambda handler, stdlib only, no LLM.

GET  -> a self-contained chat page (HTML + a dozen lines of JS).
POST -> {"reply": "..."} chosen by a handful of pattern-matching rules.

It exists to be read in about a minute and to give the deploy path something
visible. Resist improving it.
"""

import base64
import json
import random

GREETING = "Hey! I'm a chatbot. Chitty chitty chop chop."

# (keywords, replies): the first rule with a keyword in the message wins.
# Single-word keywords match whole words; phrases match as substrings.
RULES = [
    (("hello", "hi", "hey", "howdy", "greetings"), [
        "Hello hello! Chitty chitty chop chop.",
        "Hey there. I was just sitting here, being serverless.",
    ]),
    (("help",), [
        "Try saying hi, ask what I am, or type anything else and enjoy the fallback.",
    ]),
    (("what are you", "who are you", "are you an ai", "are you a bot"), [
        "I'm the world's tiniest chatbot: one Lambda, zero neurons, all canned replies.",
        "A teaching artifact. Every word I say is hardcoded in a file you can read.",
    ]),
    (("bye", "goodbye", "see you", "later"), [
        "Bye! Chitty chitty chop chop.",
        "See you. I'll be here, scaled to zero.",
    ]),
]

FALLBACK = [
    "Chitty chitty chop chop! (I know about four things. That wasn't one of them.)",
    "Hmm. My entire brain is a Python list, and you just went off-list.",
    "No idea, but confidently: chitty chitty chop chop.",
]


def reply_to(message):
    msg = message.lower()
    words = msg.split()
    for keywords, replies in RULES:
        if any(k in words if " " not in k else k in msg for k in keywords):
            return random.choice(replies)
    return random.choice(FALLBACK)


PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tiny Chatbot</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; }
  #chat { border: 1px solid #ccc; border-radius: 8px; height: 60vh; overflow-y: auto; padding: 1rem; }
  #chat p { max-width: 80%; padding: .5rem .75rem; border-radius: 8px; margin: .5rem 0; }
  .bot { background: #eee; }
  .you { background: #d9e8ff; margin-left: auto; }
  form { display: flex; gap: .5rem; margin-top: .75rem; }
  input { flex: 1; padding: .5rem; font: inherit; }
</style>
<h1>Tiny Chatbot</h1>
<div id="chat"></div>
<form id="say">
  <input id="msg" autocomplete="off" placeholder="Say something..." autofocus>
  <button>Send</button>
</form>
<script>
  const chat = document.getElementById("chat");
  const add = (who, text) => {
    const p = document.createElement("p");
    p.className = who;
    p.textContent = text;
    chat.appendChild(p);
    chat.scrollTop = chat.scrollHeight;
  };
  add("bot", __GREETING__);
  document.getElementById("say").addEventListener("submit", async (e) => {
    e.preventDefault();
    const box = document.getElementById("msg");
    const text = box.value.trim();
    if (!text) return;
    add("you", text);
    box.value = "";
    const res = await fetch(location.href, { method: "POST", body: JSON.stringify({ message: text }) });
    add("bot", (await res.json()).reply);
  });
</script>
""".replace("__GREETING__", json.dumps(GREETING))


def handler(event, context):
    """Lambda Function URL handler: GET serves the page, POST answers a message."""
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method != "POST":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "body": PAGE,
        }
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        message = str(json.loads(body).get("message", ""))
    except (json.JSONDecodeError, AttributeError):
        message = ""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"reply": reply_to(message)}),
    }
