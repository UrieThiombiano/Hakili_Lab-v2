# Checklist de mise en service — Hakili Lab

Runbook linéaire à suivre une fois. Guide complet et explications : `deploy/README.md`.
Remplacer tous les `<…>`. Cocher au fur et à mesure.

## À avoir en main avant de commencer

- [ ] PR #1 mergée dans `main` (sinon déployer `fastapi-react`)
- [ ] Nom de compte SSH du serveur (demandé à l'admin `HakiliLab`) + mot de passe (`Tuto deploiement Heztner.txt`)
- [ ] URL Neon de production : `postgresql://…@….neon.tech/…?sslmode=require`
- [ ] Clés API : `ANTHROPIC_API_KEY` (obligatoire), `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `MISTRAL_API_KEY`, `OPENAI_API_KEY`
- [ ] IDs des deux Google Sheets : `GOOGLE_SHEET_ELEVES_ID`, `GOOGLE_SHEET_PERSONNEL_ID`
- [ ] Fichier `credentials/service_account.json` (compte de service Google) sur ton poste
- [ ] Sous-domaine choisi (ex. `correction.hakililab.com`) + accès DNS pour créer un enregistrement `A`
- [ ] Confirmation admin que le port `8011` est toujours libre

---

## 1. Bascule Neon — une seule fois (depuis ton poste)

> Objectif : Alembic adopte le schéma déjà présent sur Neon sans le recréer.
> Vérification détaillée (branche Neon de test, diff colonne à colonne) : `deploy/bascule_neon.md`.

- [ ] Créer une **branche Neon** à partir de la prod (console Neon)
- [ ] Comparer le schéma attendu et le schéma réel sur cette branche :
      ```bash
      cd backend
      DATABASE_URL="<url_branche_neon_test>" python -m alembic -c alembic.ini upgrade head --sql > /tmp/attendu.sql
      pg_dump --schema-only "<url_branche_neon_test>" > /tmp/reel.sql
      # les 13 tables referentiel_*/suivi_* doivent décrire le même schéma
      ```
- [ ] Écarts éventuels corrigés dans `backend/app/models/` **avant** de stamper
- [ ] Sauvegarde de la base de prod (console Neon)
- [ ] Stamp contre la **vraie** base :
      ```bash
      cd backend
      DATABASE_URL="<url_neon_prod>" python -m alembic -c alembic.ini stamp head
      ```

---

## 2. DNS — une seule fois

- [ ] Enregistrement `A` : `<sous-domaine>` → `167.233.234.219`
- [ ] Propagation vérifiée : `dig +short <sous-domaine>` renvoie `167.233.234.219`

---

## 3. Serveur — premier déploiement

```bash
ssh <compte>@167.233.234.219

# 3.1 — Node (une seule fois, s'il n'est pas déjà là)
node -v || { curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash - && sudo apt-get install -y nodejs; }

# 3.2 — Cloner
git clone https://github.com/UrieThiombiano/Hakili_Lab-v2.git ~/hakili-lab
cd ~/hakili-lab
git checkout main          # ou: fastapi-react si PR #1 pas encore mergée

# 3.3 — Config
cp .env.example .env
chmod 600 .env
nano .env
```

Dans `.env`, renseigner **au minimum** :

```env
DEBUG=false
HAKILI_ACCES_LIBRE=false
SECRET_KEY=<coller le résultat de la commande ci-dessous>
DATABASE_URL=postgresql://…@….neon.tech/…?sslmode=require
ANTHROPIC_API_KEY=sk-ant-…
GOOGLE_API_KEY=…
DEEPSEEK_API_KEY=…
MISTRAL_API_KEY=…
OPENAI_API_KEY=…
GOOGLE_SERVICE_ACCOUNT_FILE=credentials/service_account.json
GOOGLE_SHEET_ELEVES_ID=…
GOOGLE_SHEET_PERSONNEL_ID=…
```

```bash
# 3.4 — Générer SECRET_KEY (obligatoire hors DEBUG), la coller dans .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

```bash
# 3.5 — Depuis TON POSTE (nouveau terminal), déposer le compte de service Google
scp credentials/service_account.json <compte>@167.233.234.219:~/hakili-lab/credentials/
ssh <compte>@167.233.234.219 chmod 600 ~/hakili-lab/credentials/service_account.json
```

```bash
# 3.6 — Déployer (de retour sur le serveur, dans ~/hakili-lab)
bash deploy/deploy.sh main        # ou: bash deploy/deploy.sh fastapi-react
```

- [ ] Le script se termine sur `API en ligne sur 127.0.0.1:8011 — OK`

---

## 4. Caddy — une seule fois

```bash
sudo nano /etc/caddy/Caddyfile
```

Coller à la fin (domaine remplacé) :

```
<sous-domaine> {
    reverse_proxy localhost:8011
    encode zstd gzip
}
```

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy        # reload, PAS restart
```

- [ ] `sudo systemctl status caddy` → `active (running)`

---

## 5. Vérification

```bash
curl -s https://<sous-domaine>/api/sante        # attendu : {"ok":true}
```

- [ ] `/api/sante` répond `{"ok": true}` en HTTPS
- [ ] Depuis un navigateur, aller-retour réel :
      connexion nom + PIN → dépôt d'une copie → relecture transcription →
      validation des notes → génération d'un plan → génération d'une fiche PDF

---

## Mises à jour suivantes

```bash
ssh <compte>@167.233.234.219
cd ~/hakili-lab && bash deploy/deploy.sh
```

## Retour arrière

```bash
cd ~/hakili-lab
git checkout <commit-precedent>
bash deploy/deploy.sh
```

## Diagnostic rapide

```bash
docker ps                        # le conteneur « hakili » tourne ?
docker logs hakili --tail 50     # erreurs de démarrage (souvent .env incomplet)
sudo journalctl -u caddy -f      # problème HTTPS / domaine
```
