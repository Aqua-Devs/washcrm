# PressureFlow CRM 🔫💧

Complete CRM-webapp voor hogedrukreinigingsbedrijven. Gebouwd met Python (Flask) + HTML/CSS/JS, database op Supabase, deployment op Render.

## Functionaliteiten

- **Dashboard** — Omzet-tracker, geplande klussen, voorraadwaarschuwingen
- **Klantbeheer** — Contactgegevens, property profiel (parkeren, waterdruk, buitenkraan), WhatsApp-integratie
- **Smart Estimator** — Diensten selecteren, m² invoeren, vervuilingsgraad, upsells, live totaalberekening
- **Offertes & Facturen** — Digitale handtekening, PDF generatie, statusflow (concept → offerte → akkoord → voltooid → factuur → betaald)
- **Voorraadbeheer** — Producten bijhouden, automatische aftrek bij klus voltooiing, visuele drempelwaarschuwingen
- **Foto's** — Voor/na foto's per project (direct vanuit camera)
- **Rollen** — Admin (volledige toegang) en Technicus (beperkt)

## Snelle Setup

### 1. Supabase Database

1. Maak een gratis project aan op [supabase.com](https://supabase.com)
2. Ga naar **SQL Editor** in je Supabase dashboard
3. Kopieer de inhoud van `supabase_setup.sql` en voer het uit
4. Ga naar **Project Settings > API** en kopieer je:
   - Project URL (bijv. `https://abc123.supabase.co`)
   - Anon public key (begint met `eyJ...`)

### 2. Render Deployment

1. Push deze code naar een Git repository (GitHub/GitLab)
2. Ga naar [render.com](https://render.com) en maak een **New Web Service**
3. Verbind je repository
4. Render detecteert automatisch de `render.yaml` configuratie
5. Voeg de environment variabelen toe:
   - `SUPABASE_URL` — Je Supabase project URL
   - `SUPABASE_KEY` — Je Supabase anon key
   - `SECRET_KEY` — Wordt automatisch gegenereerd

### 3. Eerste gebruik

1. Open de app URL van Render
2. Registreer je eerste account — dit wordt automatisch de **Admin**
3. Stel je bedrijfsgegevens in via ⚙️ Instellingen
4. Begin met klanten en metingen toevoegen!

## Lokaal draaien (development)

```bash
# Clone & install
cd pressureflow
pip install -r requirements.txt

# Environment instellen
cp .env.example .env
# Vul je Supabase credentials in in .env

# Starten
python app.py
# Open http://localhost:5000
```

## Projectstructuur

```
pressureflow/
├── app.py                 # Flask backend (alle API routes)
├── templates/
│   └── index.html         # Complete SPA frontend
├── requirements.txt       # Python dependencies
├── render.yaml           # Render deployment config
├── supabase_setup.sql    # Database schema & seed data
├── .env.example          # Environment template
└── README.md             # Deze file
```

## API Endpoints

| Methode | Route | Beschrijving |
|---------|-------|--------------|
| POST | `/api/auth/register` | Account aanmaken |
| POST | `/api/auth/login` | Inloggen |
| GET | `/api/dashboard` | Dashboard data |
| GET/POST | `/api/customers` | Klanten ophalen/aanmaken |
| GET/PUT/DELETE | `/api/customers/:id` | Klant detail/bewerken/verwijderen |
| GET/POST | `/api/services` | Diensten beheren |
| GET/POST | `/api/upsells` | Upsell items beheren |
| GET/POST | `/api/estimates` | Offertes ophalen/aanmaken |
| GET/PUT | `/api/estimates/:id` | Offerte detail/bewerken |
| POST | `/api/estimates/:id/sign` | Digitale handtekening |
| POST | `/api/estimates/:id/complete` | Klus voltooien (auto voorraad) |
| GET | `/api/estimates/:id/pdf` | PDF downloaden |
| POST | `/api/estimates/:id/photos` | Foto uploaden |
| GET/POST | `/api/inventory` | Voorraad beheren |
| POST | `/api/inventory/:id/adjust` | Voorraad aanpassen |
| GET/PUT | `/api/settings` | App instellingen |

## Tech Stack

- **Backend:** Python 3.11 + Flask
- **Frontend:** Vanilla HTML/CSS/JS (geen framework, snelle laadtijd)
- **Database:** Supabase (PostgreSQL)
- **PDF:** ReportLab
- **Auth:** JWT tokens + bcrypt
- **Hosting:** Render.com
