from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Anthropic Claude
    # Facultative à l'IMPORT, obligatoire à l'USAGE. Sans valeur par défaut, le
    # simple fait d'importer ce module exigeait la clé — or `src/integrations/
    # google_sheets.py` et `src/db/database.py` en dépendent, ce qui faisait
    # échouer `manage.py migrate`, `manage.py check` et l'affichage d'une liste
    # d'élèves sur une machine sans clé LLM, alors qu'aucun de ces chemins
    # n'appelle un modèle. L'échec reste net là où la clé sert réellement :
    # `ClaudeClient.__init__` refuse de se construire si elle est vide.
    anthropic_api_key: str = ""
    claude_model_heavy: str = "claude-sonnet-4-6"   # Sonnet 4.6 — transcription, correction, remédiation
    claude_model_light: str = "claude-sonnet-4-6"   # tâches légères (nom, JSON repair)
    claude_model_opus: str = "claude-opus-4-7"      # Opus 4.7 — diagnostic (raisonnement approfondi)

    # Google Gemini (vision — gratuit jusqu'à 1 M tokens/jour)
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    # "gemini" | "claude" — provider utilisé pour la transcription
    vision_provider: str = "claude"

    # Providers par étape du pipeline (indépendants des clés API)
    # grading_provider    : "deepseek" | "claude"
    # diagnostic_provider : "deepseek" | "mistral" | "claude"
    grading_provider: str = "deepseek"
    diagnostic_provider: str = "claude"

    # DeepSeek (correction V3 + diagnostic R1)
    deepseek_api_key: str = ""
    deepseek_model_v3: str = "deepseek-chat"       # DeepSeek V3 — correction
    deepseek_model_r1: str = "deepseek-reasoner"   # DeepSeek R1 — diagnostic

    # Mistral (remédiation + transcription vision via Pixtral)
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"
    mistral_vision_model: str = "pixtral-12b-2409"

    # OpenAI (filet de secours GPT-5 — remplace Claude comme fallback partout
    # où un fallback existe : transcription, nom élève, correction, diagnostic,
    # remédiation. Claude reste seul utilisé là où il n'y a pas d'alternative :
    # extraction sujet/barème, barème virtuel, enrichissement 20/20.)
    openai_api_key: str = ""
    openai_model: str = "gpt-5"

    # Seuils pipeline
    confidence_review_threshold: float = 0.75

    # Stockage
    runs_dir: str = "./runs"
    subject: str = "mathematics"

    # Base de données (Neon Postgres — portail de consultation, optionnel)
    database_url: str = ""
    debug: bool = False

    hakili_acces_libre: bool = False

    # Clé de signature des jetons d'URL opaques (`backend/app/auth/tokens.py`
    # — élève/copie/session jamais en clair dans un lien, D-CEO-25). Facultative
    # hors DEBUG (repli de dev non secret) ; `tokens.py` refuse de signer un
    # jeton sans elle une fois DEBUG=false, plutôt que de tourner avec une clé
    # publique connue de quiconque lit ce dépôt.
    secret_key: str = ""

    # Google Sheets (source de vérité élèves/personnel, compte de service —
    # optionnel). Le personnel (enseignants, responsables, administrateur)
    # vit dans un SEUL Sheet fusionné — le rôle de chaque personne vient de
    # sa colonne "role", plus d'un fichier séparé par rôle (voir
    # src/integrations/google_sheets.py).
    google_service_account_file: str = ""
    google_sheet_eleves_id: str = ""
    google_sheet_personnel_id: str = ""


settings = Settings()
