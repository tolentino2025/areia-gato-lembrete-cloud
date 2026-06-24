#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lembrete diário de limpeza da areia do gato via WhatsApp Cloud API (Meta).

SEM dados pessoais no código (seguro para repositório público):
as pessoas (nomes + telefones) vêm do Secret WHATSAPP_PEOPLE (JSON).

Variáveis de ambiente (GitHub Secrets):
  WHATSAPP_TOKEN            (obrigatório)  token permanente da Cloud API
  WHATSAPP_PHONE_NUMBER_ID  (obrigatório)  ID do número remetente
  WHATSAPP_PEOPLE           (obrigatório)  JSON: [{"nome":"X","phone":"5519..."}, ...]
                                           A ORDEM define a rotação (índice 0,1,2,3...).
  WHATSAPP_TEMPLATE_NAME    (opcional)     padrão: lembrete_areia_gato
  WHATSAPP_LANGUAGE_CODE    (opcional)     padrão: pt_BR

Uso:
  python enviar_areia_gato.py                  # responsável de HOJE (America/Sao_Paulo)
  python enviar_areia_gato.py --dry-run        # mostra quem é, sem enviar
  python enviar_areia_gato.py --data 2026-06-23  # simula a data (escolhe a pessoa)
  python enviar_areia_gato.py --todos          # envia para todos (teste)
"""

import json, os, sys, argparse, urllib.request, urllib.error
from datetime import date, datetime, timezone, timedelta

GRAPH_VERSION = "v25.0"

# Âncora da rotação: segunda 22/06/2026 = índice 0 (primeira pessoa da lista).
ANCHOR = date(2026, 6, 22)

def carregar_config():
    tok = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    people_raw = os.environ.get("WHATSAPP_PEOPLE")
    # fallback local opcional: ~/.areia-gato/secrets.json com as mesmas chaves
    local = os.path.expanduser("~/.areia-gato/secrets.json")
    if (not tok or not phone_id or not people_raw) and os.path.exists(local):
        s = json.load(open(local, encoding="utf-8"))
        tok = tok or s.get("access_token")
        phone_id = phone_id or s.get("phone_number_id")
        if not people_raw and s.get("people"):
            people_raw = json.dumps(s["people"])
    if not tok:
        sys.exit("ERRO: WHATSAPP_TOKEN ausente.")
    if not phone_id:
        sys.exit("ERRO: WHATSAPP_PHONE_NUMBER_ID ausente.")
    if not people_raw:
        sys.exit("ERRO: WHATSAPP_PEOPLE ausente (JSON com nomes e telefones).")
    try:
        people = json.loads(people_raw)
        assert isinstance(people, list) and people
    except Exception as e:
        sys.exit(f"ERRO: WHATSAPP_PEOPLE inválido: {e}")
    return {
        "access_token": tok.strip(),
        "phone_number_id": str(phone_id).strip(),
        "people": people,
        "template_name": os.environ.get("WHATSAPP_TEMPLATE_NAME", "lembrete_areia_gato"),
        "language_code": os.environ.get("WHATSAPP_LANGUAGE_CODE", "pt_BR"),
    }

def hoje_sp():
    return (datetime.now(timezone.utc) - timedelta(hours=3)).date()

def responsavel(cfg, d):
    n = len(cfg["people"])
    idx = ((d - ANCHOR).days % n + n) % n
    return cfg["people"][idx]

def enviar(cfg, pessoa):
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{cfg['phone_number_id']}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": str(pessoa["phone"]),
        "type": "template",
        "template": {
            "name": cfg["template_name"],
            "language": {"code": cfg["language_code"]},
            "components": [
                {"type": "body",
                 "parameters": [{"type": "text", "text": pessoa["nome"]}]}
            ],
        },
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Authorization", f"Bearer {cfg['access_token']}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode("utf-8"))
        mid = (resp.get("messages") or [{}])[0].get("id", "?")
        print(f"OK - enviado para {pessoa['nome']} - message id: {mid}")
        return True
    except urllib.error.HTTPError as e:
        print(f"FALHA ({e.code}) para {pessoa['nome']}: {e.read().decode('utf-8','replace')}")
        return False
    except Exception as e:
        print(f"ERRO de rede para {pessoa['nome']}: {e}")
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--todos", action="store_true")
    ap.add_argument("--data")
    args = ap.parse_args()

    cfg = carregar_config()
    d = date.fromisoformat(args.data) if args.data else hoje_sp()
    dias = ["segunda","terca","quarta","quinta","sexta","sabado","domingo"]
    print(f"Data: {d.isoformat()} ({dias[d.weekday()]}) - fuso America/Sao_Paulo")

    alvos = cfg["people"] if args.todos else [responsavel(cfg, d)]
    if not args.todos:
        print(f"Responsavel do dia: {alvos[0]['nome']}")

    if args.dry_run:
        for p in alvos:
            print(f"  (dry-run) enviaria para {p['nome']}")
        return

    ok = all(enviar(cfg, p) for p in alvos)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
