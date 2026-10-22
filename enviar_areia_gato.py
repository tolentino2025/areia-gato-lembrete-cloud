#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lembrete diário de limpeza da areia do gato via WhatsApp Cloud API (Meta).

SEM dados pessoais no código (seguro para repositório público):
as pessoas (nomes + telefones) vêm do Secret WHATSAPP_PEOPLE (JSON).

Três tipos de mensagem:
  1. LEMBRETE  -> só para o responsável do dia, no horário dele (8/9h ou 14h)
  2. AVISO     -> para os OUTROS 3, sempre às 8h, dizendo de quem é o dia
  3. ESCALA    -> para todos, segunda às 7h, com a semana inteira

Variáveis de ambiente (GitHub Secrets):
  WHATSAPP_TOKEN            (obrigatório)  token permanente da Cloud API
  WHATSAPP_PHONE_NUMBER_ID  (obrigatório)  ID do número remetente
  WHATSAPP_PEOPLE           (obrigatório)  JSON: [{"nome":"X","phone":"5519..."}, ...]
                                           A ORDEM define a rotação (índice 0,1,2,3...).
  WHATSAPP_TEMPLATE_NAME    (opcional)     padrão: lembrete_areia_gato
  WHATSAPP_TEMPLATE_AVISO   (opcional)     padrão: aviso_dia_areia_gato
  WHATSAPP_TEMPLATE_ESCALA  (opcional)     padrão: escala_semanal_areia_gato
  WHATSAPP_LANGUAGE_CODE    (opcional)     padrão: pt_BR

Uso:
  python enviar_areia_gato.py --hora 8 --aviso   # lembrete + aviso aos demais
  python enviar_areia_gato.py --hora 9           # só o lembrete (repetição)
  python enviar_areia_gato.py --escala           # escala da semana para todos
  python enviar_areia_gato.py --dry-run          # mostra o que faria, sem enviar
  python enviar_areia_gato.py --data 2026-10-22  # simula a data
"""

import json, os, sys, argparse, urllib.request, urllib.error
from datetime import date, datetime, timezone, timedelta

GRAPH_VERSION = "v25.0"

# Âncora da rotação: segunda 22/06/2026 = índice 0 (primeira pessoa da lista).
ANCHOR = date(2026, 6, 22)

# Horários do LEMBRETE pessoal, por pessoa (hora local America/Sao_Paulo).
HORAS_POR_NOME = {
    "Thais":    [8, 9],
    "Cleiton":  [8, 9],
    "Laurinha": [14],
    "Isabella": [8, 9],
}
DEFAULT_HORAS = [14]

DIAS_PT = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


def horas_da_pessoa(nome):
    return HORAS_POR_NOME.get(nome, DEFAULT_HORAS)


def horas_texto(nome):
    h = horas_da_pessoa(nome)
    if len(h) == 1:
        return f"{h[0]}h"
    return " e ".join(f"{x}h" for x in h)


def carregar_config():
    tok = os.environ.get("WHATSAPP_TOKEN")
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    people_raw = os.environ.get("WHATSAPP_PEOPLE")
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
        "access_token": "".join(str(tok).split()),
        "phone_number_id": "".join(str(phone_id).split()),
        "people": people,
        "template_name": os.environ.get("WHATSAPP_TEMPLATE_NAME", "lembrete_areia_gato"),
        "template_aviso": os.environ.get("WHATSAPP_TEMPLATE_AVISO", "aviso_dia_areia_gato"),
        "template_escala": os.environ.get("WHATSAPP_TEMPLATE_ESCALA", "escala_semanal_areia_gato"),
        "language_code": os.environ.get("WHATSAPP_LANGUAGE_CODE", "pt_BR"),
    }


def hoje_sp():
    return (datetime.now(timezone.utc) - timedelta(hours=3)).date()


def responsavel(cfg, d):
    n = len(cfg["people"])
    idx = ((d - ANCHOR).days % n + n) % n
    return cfg["people"][idx]


def data_texto(d):
    """Ex.: '22/10 (quinta)'. Sem quebra de linha - vai como parametro."""
    return f"{d.strftime('%d/%m')} ({DIAS_PT[d.weekday()]})"


def escala_semana(cfg, d):
    """7 strings (segunda..domingo) da semana que contem a data d.

    Cada item vira um parametro {{N}} do template. Parametros de template
    NAO podem conter quebra de linha, tab ou 4+ espacos seguidos.
    """
    seg = d - timedelta(days=d.weekday())
    itens = []
    for i in range(7):
        dia = seg + timedelta(days=i)
        p = responsavel(cfg, dia)
        itens.append(f"{dia.strftime('%d/%m')} - {p['nome']} ({horas_texto(p['nome'])})")
    return itens


def _post(cfg, payload, destino, rotulo):
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{cfg['phone_number_id']}/messages"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Authorization", f"Bearer {cfg['access_token']}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode("utf-8"))
        mid = (resp.get("messages") or [{}])[0].get("id", "?")
        print(f"OK - {rotulo} enviado para {destino} - message id: {mid}")
        return True
    except urllib.error.HTTPError as e:
        print(f"FALHA ({e.code}) {rotulo} para {destino}: {e.read().decode('utf-8','replace')}")
        return False
    except Exception as e:
        print(f"ERRO de rede ({rotulo}) para {destino}: {e}")
        return False


def _template(cfg, pessoa, nome_template, params):
    return {
        "messaging_product": "whatsapp",
        "to": str(pessoa["phone"]),
        "type": "template",
        "template": {
            "name": nome_template,
            "language": {"code": cfg["language_code"]},
            "components": [
                {"type": "body",
                 "parameters": [{"type": "text", "text": t} for t in params]}
            ],
        },
    }


def enviar_lembrete(cfg, pessoa):
    p = _template(cfg, pessoa, cfg["template_name"], [pessoa["nome"]])
    return _post(cfg, p, pessoa["nome"], "lembrete")


def enviar_aviso(cfg, pessoa, d, nome_responsavel):
    p = _template(cfg, pessoa, cfg["template_aviso"], [data_texto(d), nome_responsavel])
    return _post(cfg, p, pessoa["nome"], "aviso")


def enviar_escala(cfg, pessoa, itens):
    p = _template(cfg, pessoa, cfg["template_escala"], itens)
    return _post(cfg, p, pessoa["nome"], "escala")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--todos", action="store_true",
                    help="envia o lembrete para todos (teste)")
    ap.add_argument("--aviso", action="store_true",
                    help="envia tambem o aviso 'hoje e a vez de X' aos DEMAIS")
    ap.add_argument("--escala", action="store_true",
                    help="envia a escala da semana corrente para TODOS")
    ap.add_argument("--data")
    ap.add_argument("--hora", help="slot de hora SP (8, 9, 14). Vazio = envia sempre.")
    args = ap.parse_args()

    cfg = carregar_config()
    d = date.fromisoformat(args.data) if args.data else hoje_sp()
    print(f"Data: {d.isoformat()} ({DIAS_PT[d.weekday()]}) - fuso America/Sao_Paulo")

    # ---------- 3. escala semanal para todos ----------
    if args.escala:
        itens = escala_semana(cfg, d)
        seg = d - timedelta(days=d.weekday())
        print(f"Escala da semana {seg.strftime('%d/%m')} a "
              f"{(seg + timedelta(days=6)).strftime('%d/%m')}:")
        for nome_dia, item in zip(DIAS_PT, itens):
            print(f"  {nome_dia:<8} {item}")
        if args.dry_run:
            print("  (dry-run) nada enviado.")
            return
        ok = all(enviar_escala(cfg, p, itens) for p in cfg["people"])
        sys.exit(0 if ok else 1)

    resp = responsavel(cfg, d)
    horas = horas_da_pessoa(resp["nome"])
    print(f"Responsavel do dia: {resp['nome']} (lembrete as {horas_texto(resp['nome'])})")

    slot = None
    if args.hora not in (None, ""):
        try:
            slot = int(args.hora)
        except ValueError:
            slot = None

    ok = True

    # ---------- 2. aviso aos DEMAIS (de quem e o dia) ----------
    if args.aviso:
        outros = [p for p in cfg["people"] if str(p["phone"]) != str(resp["phone"])]
        print(f"Aviso do dia -> {len(outros)} pessoas "
              f"(texto: '{data_texto(d)}' / '{resp['nome']}')")
        if args.dry_run:
            for p in outros:
                print(f"  (dry-run) aviso para {p['nome']}")
        else:
            ok = all(enviar_aviso(cfg, p, d, resp["nome"]) for p in outros) and ok

    # ---------- 1. lembrete pessoal do responsavel ----------
    if args.todos:
        alvos = cfg["people"]
    elif slot is not None and slot not in horas:
        print(f"Slot {slot}h nao e horario de {resp['nome']} ({horas_texto(resp['nome'])}). "
              f"Sem lembrete pessoal agora.")
        alvos = []
    else:
        alvos = [resp]

    if args.dry_run:
        for p in alvos:
            print(f"  (dry-run) lembrete para {p['nome']}")
        return

    for p in alvos:
        ok = enviar_lembrete(cfg, p) and ok

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
