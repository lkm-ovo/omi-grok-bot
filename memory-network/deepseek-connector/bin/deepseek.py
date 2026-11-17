#!/usr/bin/env python3
"""DeepSeek API helper using the registered custom.deepseek credential.

Usage:
  python3 deepseek.py models
  python3 deepseek.py chat --model deepseek-flash --message "hello" [--system "you are helpful"]
"""
import argparse
import json
import sys
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def call(method, path, payload=None):
    url = f"https://api.deepseek.com{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    add_surrogate_to_request(req, "custom.deepseek", allowed_hosts=["api.deepseek.com"])
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=60) as resp:
        return read_json_response(resp)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models")
    chat = sub.add_parser("chat")
    chat.add_argument("--model", default="deepseek-flash")
    chat.add_argument("--message", required=True)
    chat.add_argument("--system", default="")
    chat.add_argument("--temperature", type=float, default=0.7)
    chat.add_argument("--max-tokens", type=int, default=800)
    args = parser.parse_args()

    if args.cmd == "models":
        print(json.dumps(call("GET", "/v1/models"), ensure_ascii=False, indent=2))
        return

    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": args.message})
    result = call("POST", "/v1/chat/completions", {
        "model": args.model,
        "messages": messages,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
