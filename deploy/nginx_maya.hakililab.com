# Vhost nginx pour Hakili Lab (correction assistée) — à placer par l'admin dans :
#   /etc/nginx/sites-available/maya.hakililab.com
# puis :
#   sudo ln -s /etc/nginx/sites-available/maya.hakililab.com /etc/nginx/sites-enabled/
#   sudo nginx -t && sudo systemctl reload nginx
#   sudo certbot --nginx -d maya.hakililab.com      # ajoute le bloc 443 + redirection 80->443
#   sudo nginx -t && sudo systemctl reload nginx
#
# Prérequis : enregistrement DNS  A  maya.hakililab.com -> 167.233.234.219 (fait).
# Le conteneur `hakili` écoute sur 127.0.0.1:8017 (deploy/deploy.sh, HAKILI_PORT=8017).
# Même modèle que les autres sous-domaines du serveur (apurmed, amira, parcours…).

server {
    listen 80;
    listen [::]:80;
    server_name maya.hakililab.com;

    # Dépôt de copies scannées : jusqu'à 50 Mo par fichier côté application
    # (backend/app/services/corrections.py::TAILLE_MAX), plusieurs fichiers par
    # envoi en dépôt par lot. Le défaut nginx (1 Mo) renverrait une 413.
    client_max_body_size 200m;

    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;

    location / {
        proxy_pass http://127.0.0.1:8017;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        # Indispensable : sans lui l'application redirige en boucle vers HTTPS
        # (backend/app/security.py::SecuriteProductionMiddleware).
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # Envoi de scans volumineux sur une connexion lente, et génération de
        # documents (PDF, sujets) servie à la demande : délais larges.
        proxy_request_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
