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
  python enviar_areia_gato.py                     # responsavel de HOJE (America/Sao_Paulo)
  python enviar_areia_gato.py --dry-run           # mostra quem e, sem enviar
  python enviar_areia_gato.py --data 2026-06-23   # simula a data (escolhe a pessoa)
  python enviar_areia_gato.py --hora 8            # so envia se 8h for horario da pessoa
  python enviar_areia_gato.py --todos             # envia para todos (teste)
"""

import json, os, sys, argparse, urllib.request, urllib.error
from datetime import date, datetime, timezone, timedelta

GRAPH_VERSION = "v25.0"

# Ancora da rotacao: segunda 22/06/2026 = indice 0 (primeira pessoa da lista).
ANCHOR = date(2026, 6, 22)

# Horarios de envio por pessoa (hora local America/Sao_Paulo).
# Cleiton, Thais e Isabella: 8h e repete 9h. Laurinha: 14h.
HORAS_POR_NOME = {
    "Thais":    [8, 9],
    "Cleiton":  [8, 9],
    "Laurinha": [14],
    "Isabella": [8, 9],
}
DEFAULT_HORAS = [14]

def horas_da_pessoa(nome):
    return HORAS_POR_NOME.get(nome, DEFAULT_HORAS)

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
        sys.exit(f"ERRO: WHATSAPP_PEOPLE invalido: {e}")
    return {
        "access_token": "".join(str(tok).split()),  # remove espacos/quebras de linha
        "phone_number_id": "".join(str(phone_id).split()),
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
    ap.add_argument("--hora", help="slot de hora SP (8, 9, 14). Vazio = envia sempre.")
    args = ap.parse_args()

    cfg = carregar_config()
    d = date.fromisoformat(args.data) if args.data else hoje_sp()
    dias = ["segunda","terca","quarta","quinta","sexta","sabado","domingo"]
    print(f"Data: {d.isoformat()} ({dias[d.weekday()]}) - fuso America/Sao_Paulo")

    alvos = cfg["people"] if args.todos else [responsavel(cfg, d)]
    if not args.todos:
        p = alvos[0]
        horas = horas_da_pessoa(p["nome"])
        print(f"Responsavel do dia: {p['nome']} (horarios: {horas}h)")
        # Se veio de um slot agendado, so envia se o horario for da pessoa.
        if args.hora not in (None, ""):
            try:
                slot = int(args.hora)
            except ValueError:
                slot = None
            if slot not in horas:
                print(f"Slot {args.hora}h nao e horario de {p['nome']} ({horas}h). Nada a enviar.")
                return

    if args.dry_run:
        for p in alvos:
            print(f"  (dry-run) enviaria para {p['nome']}")
        return

    ok = all(enviar(cfg, p) for p in alvos)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
