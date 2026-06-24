# Lembrete Areia do Gato

Envia, todo dia às **14:00 (America/Sao_Paulo)**, um lembrete de WhatsApp para o
responsável do dia (rotação contínua), via **WhatsApp Cloud API**, rodando no
GitHub Actions — sem depender de nenhuma máquina ligada.

**Sem dados pessoais no código.** Nomes e telefones ficam no Secret `WHATSAPP_PEOPLE`.

## Secrets necessários (Settings → Secrets and variables → Actions)
- `WHATSAPP_TOKEN` — token permanente da Cloud API
- `WHATSAPP_PHONE_NUMBER_ID` — ID do número remetente
- `WHATSAPP_PEOPLE` — JSON com a ordem da rotação, ex.:
  `[{"nome":"Thais","phone":"55..."},{"nome":"Cleiton","phone":"55..."}, ...]`

## Testar
Actions → **Lembrete Areia do Gato** → **Run workflow** (campo de data opcional
`AAAA-MM-DD` para escolher a pessoa daquele dia).

Rotação: âncora segunda 22/06/2026 = primeira pessoa da lista; índice = dias desde a âncora mod nº de pessoas.
